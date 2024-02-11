import os
import shelve

from threading import Thread, RLock
from queue import Queue, Empty
from collections import defaultdict
from urllib.parse import urlparse, urlunparse

from utils import get_logger, get_urlhash, normalize
from scraper import is_valid

import time
import re
from hashlib import sha256


# Current problems
#   http://plrg.ics.uci.edu/publications/{number}.bib
#       a bunch of publications that follow this pattern, trash(?) data

class Frontier(object):
    def __init__(self, config, restart, query_limit=40, depth_limit=15, queue_count=20):
        self.logger = get_logger("FRONTIER")
        self.config = config
        self.to_be_downloaded = Queue()

        # The list of URL queues. Each domain is put into the same queue, and each queue is assigned its own time delay
        #   to enforce politeness.
        self.tbd = list()

        self.queue_count = queue_count
        for i in range(queue_count):
            self.tbd.append(Queue())
        self.queue_timestamps = list()
        #t = time.time() * 1000
        for i in range(queue_count):
            self.queue_timestamps.append(0)
        self.next_tbd = 0
        self.tbd_count = 0
        self.tbd_count_lock = RLock()
        self.add_lock = RLock()
        self.pop_lock = RLock()
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
    
    def increment_tbd(self):
        self.tbd_count_lock.acquire()
        try:
            self.tbd_count += 1
        finally:
            self.tbd_count_lock.release()
        # print(self.tbd_count)

    def decrement_tbd(self):
        self.tbd_count_lock.acquire()
        try:
            self.tbd_count -= 1
        finally:
            self.tbd_count_lock.release()
        # print(self.tbd_count)
    
    def get_tbd_count(self):
        # ret = None
        # self.tbd_count_lock.acquire()
        # try:
        #     ret = self.tbd_count
        # finally:
        #     self.tbd_count_lock.release()
        # return ret
        count = 0
        for queue in self.tbd:
            count += queue.qsize()
        return count

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
        self.pop_lock.acquire()
        try:
            i = self.next_tbd
            self.next_tbd = (self.next_tbd + 1) % self.queue_count
            d = None
            while True:
                # print(self.next_tbd)
                elapsed_time = (time.time() - self.queue_timestamps[self.next_tbd])
                #if (self.tbd[self.next_tbd].qsize() > 0) and (d == None or elapsed_time > d):
                if (d == None or elapsed_time > d):
                    d = elapsed_time
                if (self.tbd[self.next_tbd].qsize() > 0) and (elapsed_time > self.config.time_delay or elapsed_time < 0):
                    print(f'taking from queue {self.next_tbd}')
                    self.decrement_tbd()
                    self.queue_timestamps[self.next_tbd] = time.time()
                    ret = self.tbd[self.next_tbd].get()
                    # print(f'ret: {ret}')
                    # self.logger.info(
                    #     f'Popped {ret} from queue #{self.next_tbd}.'
                    # )
                    return ret
                if self.next_tbd == i:
                    break
                self.next_tbd = (self.next_tbd + 1) % self.queue_count
            print(f'no available queues; {d}')
            for queue in self.tbd:
                print(queue.qsize(), end=', ')
            print()
            # for t in self.queue_timestamps:
            #     print((time.time() - t) * 1000, end=', ')
            # print()
            # if time.time() - self.queue_timestamps[self.next_tbd] > self.config.time_delay:
            #     self.queue_timestamps[self.next_tbd] = time.time()
            #     self.next_tbd = (self.next_tbd + 1) % self.queue_count
            #     self.decrement_tbd()
            #     print('a')
            #     print(f'ret: {ret}')
            #     return ret
            # else:
            #     return None
            #return self.to_be_downloaded.get(timeout=5)
        except Empty:
            self.logger.info('No URL returned.')
            return None
        except Exception:
            self.logger.info('a')
        finally:
            self.pop_lock.release()

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
                    # print(url)
                    no_query = parse._replace(query='')
                    self.add_url(no_query.geturl())
                    # print(self.query_counts[no_query.geturl()])
                    if self.query_counts[no_query.geturl()] < self.query_limit:
                        self.query_counts[no_query.geturl()] += 1
                    else:
                        valid = False
                        # print('too many queries!')

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
                domain = parse.netloc

                # get just the ***.uci.edu domain if it's one of those domains
                d_match = re.search('([a-zA-Z0-9]{2,}\.[a-zA-Z0-9]{2,}\.[a-zA-Z0-9]{2,}$)', domain)
                if d_match:
                    domain = d_match.group(1)
                # domain hash to put into queue list
                domain_hash = int(sha256(domain.encode('utf-8')).hexdigest(), 16)
                
                self.add_lock.acquire()

                try:
                    self.tbd[domain_hash % self.queue_count].put(url)
                    self.increment_tbd()
                    self.save[urlhash] = (url, False)
                    self.save.sync()
                    self.to_be_downloaded.put(url)
                    # self.logger.info(f'Added {url} to frontier.')
                finally:
                    self.add_lock.release()
    
    def mark_url_complete(self, url):
        urlhash = get_urlhash(url)
        if urlhash not in self.save:
            # This should not happen.
            self.logger.error(
                f"Completed url {url}, but have not seen it before.")

        self.save[urlhash] = (url, True)
        self.save.sync()
