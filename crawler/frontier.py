import os
import shelve

from threading import Thread, RLock
from queue import Queue, Empty
from collections import defaultdict
from urllib.parse import urlparse, urlunparse

from utils import get_logger, get_urlhash, normalize
from scraper import is_valid

# Current problems
#   http://plrg.ics.uci.edu/publications/{number}.bib
#       a bunch of publications that follow this pattern, trash(?) data

class Frontier(object):
    def __init__(self, config, restart, query_limit=40, depth_limit=15):
        self.logger = get_logger("FRONTIER")
        self.config = config
        self.to_be_downloaded = Queue()
        # self.file_counts = defaultdict(int)
        self.query_counts = defaultdict(int)
        self.query_limit = query_limit
        self.depth_limit = depth_limit
        
        if not os.path.exists(self.config.save_file) and not restart:
            # Save file does not exist, but request to load save.
            self.logger.info(
                f"Did not find save file {self.config.save_file}, "
                f"starting from seed.")
        elif os.path.exists(self.config.save_file) and restart:
            # Save file does exists, but request to start from seed.
            self.logger.info(
                f"Found save file {self.config.save_file}, deleting it.")
            os.remove(self.config.save_file)
        # Load existing save file, or create one if it does not exist.
        self.save = shelve.open(self.config.save_file)
        if restart:
            for url in self.config.seed_urls:
                self.add_url(url)
        else:
            # Set the frontier state with contents of save file.
            self._parse_save_file()
            if not self.save:
                for url in self.config.seed_urls:
                    self.add_url(url)

    def _parse_save_file(self):
        ''' This function can be overridden for alternate saving techniques. '''
        total_count = len(self.save)
        tbd_count = 0
        for url, completed in self.save.values():
            if not completed and is_valid(url):
                self.to_be_downloaded.put(url)
                tbd_count += 1
        self.logger.info(
            f"Found {tbd_count} urls to be downloaded from {total_count} "
            f"total urls discovered.")

    def get_tbd_url(self):
        try:
            return self.to_be_downloaded.get(timeout=5)
        except Empty:
            return None

    def add_url(self, url):
        url = normalize(url)
        urlhash = get_urlhash(url)
            
        if urlhash not in self.save:
            parse = urlparse(url)
            valid = True

            # Enforce heuristics for detecting traps
            if parse.path != '':
                # Avoid links that have a lot of queries
                #   currently this is not perfect as news article queries (e.g. https://www.ics.uci.edu/community/news/view_news?id=1645)
                #       can contain important information
                #   idea: search for keywords like "news", "article" in query links and excuse them from query limits
                if parse.query != '':
                    print(url)
                    no_query = parse._replace(query='')
                    self.add_url(no_query.geturl())
                    print(self.query_counts[no_query.geturl()])
                    if self.query_counts[no_query.geturl()] < self.query_limit:
                        self.query_counts[no_query.geturl()] += 1
                    else:
                        valid = False
                        print('too many queries!')

                # Avoid going down too deep in subdirectories
                file_path = parse.path.split('/')
                if len(file_path) > self.depth_limit:
                    valid = False
                    print('too deep!')
                # parent = parse._replace(path='/'.join(file_path[:-1]))
                # print('/'.join(parent.path.split('/')[:-1]))
                # if (self.file_counts[parent.geturl()] < self.breadth_limit):
                #     self.file_counts[parent.geturl()] += 1
                # else:
                #     valid = False
                #     print('too wide!')
            if valid:
                self.save[urlhash] = (url, False)
                self.save.sync()
                self.to_be_downloaded.put(url)
    
    def mark_url_complete(self, url):
        urlhash = get_urlhash(url)
        if urlhash not in self.save:
            # This should not happen.
            self.logger.error(
                f"Completed url {url}, but have not seen it before.")

        self.save[urlhash] = (url, True)
        self.save.sync()
