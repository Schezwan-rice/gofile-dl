import argparse
import logging
import os
import requests
import hashlib
from pathvalidate import sanitize_filename
from typing import Optional
import time
import math


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s][%(funcName)20s()][%(levelname)-8s]: %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("GoFile")


class ProgressBar:
    def __init__(self, name: str, total: int):
        self.name = name
        self.total = total
        self.start_time = time.time()
        self.current = 0

    def update(self, chunk_size: int):
        self.current += chunk_size
        elapsed_time = time.time() - self.start_time
        if elapsed_time > 0:
            speed = self.current / elapsed_time / (1024 * 1024)  # MB/s
            remaining_size = (self.total - self.current) / (1024 * 1024 * 1024)  # GB
            percentage = 100 * self.current / self.total
            filled_length = int(50 * self.current / self.total)
            bar = '█' * filled_length + '-' * (50 - filled_length)
            print(f'\r{self.name}: |{bar}| {percentage:.2f}% Speed: {speed:.2f} MB/s Remaining: {remaining_size:.2f} GB', end='')
            if self.current >= self.total:
                print()


class GoFileMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


class GoFile(metaclass=GoFileMeta):
    def __init__(self) -> None:
        self.token = ""
        self.wt = ""

    def update_token(self) -> None:
        if self.token == "":
            data = requests.post("https://api.gofile.io/accounts").json()
            if data["status"] == "ok":
                self.token = data["data"]["token"]
                logger.info(f"Updated token: {self.token}")
            else:
                raise Exception("Cannot get token")

    def update_wt(self) -> None:
        if self.wt == "":
            alljs = requests.get("https://gofile.io/dist/js/alljs.js").text
            if 'wt: "' in alljs:
                self.wt = alljs.split('wt: "')[1].split('"')[0]
                logger.info(f"Updated wt: {self.wt}")
            else:
                raise Exception("Cannot get wt")

    def execute(self, dir: str, content_id: Optional[str] = None, url: Optional[str] = None, password: Optional[str] = None) -> None:
        if content_id is not None:
            self.update_token()
            self.update_wt()
            hash_password = hashlib.sha256(password.encode()).hexdigest() if password else ""
            data = requests.get(
                f"https://api.gofile.io/contents/{content_id}?wt={self.wt}&cache=true&password={hash_password}",
                headers={
                    "Authorization": "Bearer " + self.token,
                },
            ).json()
            if data["status"] == "ok":
                if data["data"].get("passwordStatus", "passwordOk") == "passwordOk":
                    if data["data"]["type"] == "folder":
                        dirname = data["data"]["name"]
                        dir = os.path.join(dir, sanitize_filename(dirname))
                        for children_id in data["data"]["childrenIds"]:
                            if data["data"]["children"][children_id]["type"] == "folder":
                                self.execute(dir=dir, content_id=children_id, password=password)
                            else:
                                filename = data["data"]["children"][children_id]["name"]
                                file = os.path.join(dir, sanitize_filename(filename))
                                link = data["data"]["children"][children_id]["link"]
                                self.download(link, file)
                    else:
                        filename = data["data"]["name"]
                        file = os.path.join(dir, sanitize_filename(filename))
                        link = data["data"]["link"]
                        self.download(link, file)
                else:
                    logger.error(f"Invalid password: {data['data'].get('passwordStatus')}")
        elif url is not None:
            if url.startswith("https://gofile.io/d/"):
                self.execute(dir=dir, content_id=url.split("/")[-1], password=password)
            else:
                logger.error(f"Invalid URL: {url}")
        else:
            logger.error(f"Invalid parameters")

    def download(self, link: str, file: str, chunk_size: int = 8192):
      try:
          dir = os.path.dirname(file)
          if not os.path.exists(dir):
              os.makedirs(dir)
          if not os.path.exists(file):
              with requests.get(
                  link, headers={"Cookie": "accountToken=" + self.token}, stream=True
              ) as r:
                  r.raise_for_status()
                  content_length = int(r.headers.get("Content-Length", 0))
                  progress_bar = ProgressBar("Downloading", content_length)
                  with open(file, "wb") as f:
                      for chunk in r.iter_content(chunk_size=chunk_size):
                          f.write(chunk)
                          progress_bar.update(len(chunk))
                  logger.info(f"Downloaded: {file} ({link})")
      except Exception as e:
          logger.error(f"Failed to download ({e}): {file} ({link})")


parser = argparse.ArgumentParser()
parser.add_argument("url")
parser.add_argument("-d", type=str, dest="dir", help="Output directory")
parser.add_argument("-p", type=str, dest="password", help="Password")
args = parser.parse_args()
if __name__ == "__main__":
    dir = args.dir if args.dir else "./output"
    GoFile().execute(dir=dir, url=args.url, password=args.password)
