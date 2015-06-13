#!/usr/bin/env python

import time
import os

import boto
import boto.ec2
import boto.exception
import dotenv

dotenv.read_dotenv()
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/43.0.2357.124 Safari/537.36"
HOME = os.environ.get('HOME')
SSH_PATH = os.path.join(HOME, '.ssh')

AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
EC2_KEY_NAME = os.environ.get('EC2_KEY_NAME', 'hacker-news-ec2')
ITEM = os.environ.get('ITEM')
INSTANCES_PER_REGION = int(os.environ.get('INSTANCES_PER_REGION', '1'))
MINUTES_TO_WAIT_BEFORE_TERMINATE_INSTANCES = int(os.environ.get('MINUTES_TO_WAIT_BEFORE_TERMINATE_INSTANCES', '2'))


amis_per_regions = {
    'ap-northeast-1': 'ami-e5be98e4',
    'ap-southeast-1': 'ami-96fda7c4',
    'eu-west-1':      'ami-84f129f3',
    'sa-east-1':      'ami-5fbb1042',
    'us-east-1':      'ami-d017b2b8',
    'us-west-1':      'ami-1fe6e95a',
    'ap-southeast-2': 'ami-4f274775',
    'us-west-2':      'ami-d9a1e6e9'
}


script = """#!/bin/bash

wget https://bootstrap.pypa.io/get-pip.py
sudo python get-pip.py
sudo pip install requests

sudo python -c '

ITEM = "%(ITEM)s"

import requests
import string
import random
import os
from urllib import urlencode


USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/43.0.2357.124 Safari/537.36"

HOME = os.environ.get('HOME')
SSH_PATH = os.path.join(HOME, '.ssh')


def id_generator(size=8, chars=string.ascii_uppercase + string.digits):
    return "".join(random.choice(chars) for _ in range(size))


def gen_string():
    return id_generator()


def vote(item):
    first_url = "https://news.ycombinator.com/vote"
    data = {"for": item, "dir": "up", "goto": "item?id=" + item}
    print first_url
    r = requests.get(first_url + "?" + urlencode(data))
    print r.status_code
    if r.status_code == 200:
        url = "https://news.ycombinator.com/vote"
        data = {
            "goto": "item?id=" + item,
            "dir": "up",
            "for": item,
            "creating": "t",
            "acct": gen_string(),
            "pw": gen_string()
        }

        headers = {
            "referer": first_url,
            "user-agent": USER_AGENT
        }
        r = requests.post(url, data, headers=headers)
        print r.status_code
        print r.content

vote(ITEM)
'
"""


class EC2Mgr:
    def __init__(self, key, secret, ec2_key_name):
        self.key = key
        self.secret = secret
        self.ec2_key_name = ec2_key_name
        self._available_amis_per_regions = None

    def initialize_key_pair(self):
        """
        try to create key pairs by region
        :return: available regions
        """
        available_regions = {}
        for region, ami in amis_per_regions.iteritems():
            try:
                ec2 = boto.ec2.connect_to_region(region, aws_access_key_id=self.key, aws_secret_access_key=self.secret)
                try:
                    key_pair = ec2.create_key_pair(self.ec2_key_name)  # only needs to be done once
                    key_pair.save(SSH_PATH)
                except boto.exception.EC2ResponseError as e:  # already exist
                    msg = "The keypair '{0}' already exists.".format(self.ec2_key_name)
                    if msg != e.message:
                        raise e
                available_regions[region] = ami
            except Exception as e:
                print " !!!! not supported. \n{0}".format(e)
        return available_regions

    @property
    def available_amis_per_regions(self):
        if not self._available_amis_per_regions:
            self._available_amis_per_regions = self.initialize_key_pair()
        return self._available_amis_per_regions

    def real_launch(self, region, item_to_vote, instances=1):
        startup = script % {'ITEM': item_to_vote}
        ips = []
        print "launching in {0}: instances: {1}".format(region, instances)
        # print startup
        try:
            ec2 = boto.ec2.connect_to_region(region, aws_access_key_id=self.key, aws_secret_access_key=self.secret)
            try:
                key_pair = ec2.create_key_pair(self.ec2_key_name)  # only needs to be done once
                key_pair.save(SSH_PATH)
            except boto.exception.EC2ResponseError as e:
                #print e
                pass
            reservation = ec2.run_instances(image_id=amis_per_regions[region],
                                            min_count=instances, max_count=instances,
                                            key_name=self.ec2_key_name,
                                            user_data=startup)
            ips.extend(self._insert_instances(reservation, ec2))

        except Exception as e:
            print " !!!! not supported. \n{0}".format(e)
        return ips

    @staticmethod
    def _all_instances_have_ip(instances):
        lst = [instance for instance in instances if instance.ip_address]
        return len(lst) == len(instances)

    def _insert_instances(self, reservation, ec2):
        """
        check every 15s if all ip addresses are ready.
        when ready insert into db
        else wait again
        :param reservation:
        :param ec2:
        :param run:
        :return:
        """
        time.sleep(15)
        ips = []
        reservations = ec2.get_all_instances()
        for r in reservations:
            if r.id == reservation.id:
                if self._all_instances_have_ip(r.instances):
                    for instance in r.instances:
                        ips.append(instance.ip_address)
                else:
                    ips.extend(self._insert_instances(reservation, ec2))
        print ips

        return ips

    def terminate_all_instances(self):
        for region, ami in self.available_amis_per_regions.iteritems():
            print "terminating in {0}: ".format(region),
            ec2 = boto.ec2.connect_to_region(region, aws_access_key_id=self.key, aws_secret_access_key=self.secret)
            reservations = ec2.get_all_instances()
            for r in reservations:
                for instance in r.instances:
                    if instance.key_name == EC2_KEY_NAME:
                        print "terminating: ", instance.key_name, instance.ip_address, "state now:", instance.state
                        instance.terminate()

def vote_for(item, instances_per_region):
    ec2mgr = EC2Mgr(key=AWS_ACCESS_KEY_ID,
                    secret=AWS_SECRET_ACCESS_KEY,
                    ec2_key_name=EC2_KEY_NAME)

    for reg in amis_per_regions.keys():
        print reg, "voting for ", item
        ec2mgr.real_launch(reg, item, instances_per_region)

    print "waiting {} minutes before terminate all instances".format(MINUTES_TO_WAIT_BEFORE_TERMINATE_INSTANCES)
    time.sleep(MINUTES_TO_WAIT_BEFORE_TERMINATE_INSTANCES*60)
    ec2mgr.terminate_all_instances()

if __name__ == '__main__':
    print "ssh path so you can ssh to your instances while running:", SSH_PATH
    if ITEM:
        vote_for(ITEM, INSTANCES_PER_REGION)
    else:
        print "please provide the item to vote in the .env file"

