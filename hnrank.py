#!/usr/bin/env python

import requests
import re
from sys import stdout
import logging
import time


MAX_PAGE = 500
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/43.0.2357.124 Safari/537.36"


class HN:
    def __init__(self, item):
        self.found = False
        self.page = -1
        self.rank = ''
        self.done = False
        self.item = item

    def reset(self):
        self.found = False
        self.page = -1
        self.rank = ''
        self.done = False

    def get_rank(self, page_content):
        pattern = re.compile('<span class="rank">\d+.</span></td>      <td><center><a id="up_{}"'.format(self.item))
        r = pattern.findall(page_content)
        return r

    def get_hn_rank(self, start_page=0):
        for i in range(start_page, MAX_PAGE):
            url = 'https://news.ycombinator.com/news?p={}'.format(i)
            stdout.write("\rprocessing: {}".format(url))
            stdout.flush()
            headers = {
                "referer": 'news.ycombinator.com',
                "user-agent": USER_AGENT
            }
            r = requests.get(url=url, headers=headers)
            while r.status_code != 200:
                print url, "give us status: {} this time".format(r.status_code)
                r = requests.get(url)

            rank = self.get_rank(r.content)
            if rank:
                self.found = True
                self.done = True
                print ("\npage: {}, rank: {}\n".format(i, rank))

                self.page = i
                self.rank = rank
                return i



hn = HN('9701704')  # Abraham
hn.get_hn_rank(370)

print '\n', hn.found, hn.page, hn.rank



