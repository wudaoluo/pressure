#!/usr/bin/env python
#coding:utf-8
#2016.12.25 carlo
#压力测试

import multiprocessing
from gevent import monkey; monkey.patch_all()
import requests,time,uuid,gevent,re,os



class LogParset(object):
    def __init__(self):
        self._microseconds = ""
        self._status_code = ""
        self._datalen = ""

    def parse(self,line):
        try:
            line_item = line.strip("\n").split(";")
            self.microseconds = line_item[0]
            self.status_code = line_item[1]
            self.datalen = line_item[2]
        except Exception:
            pass

    def to_dict(self):
        """将属性(@property)的转化为dict输出"""
        propertys = {}
        propertys['microseconds'] = self.microseconds
        propertys['status_code'] = self.status_code
        propertys['datalen'] = self.datalen
        return propertys

    #创建生成器
    def log_line_iter(self, filelist):
        for file in filelist:
            with open(file, 'rb') as f:
                for line in f:
                    self.parse(line)
                    yield self.to_dict()

    @property
    def microseconds(self):
        return self._microseconds

    @microseconds.setter
    def microseconds(self,microseconds):
        self._microseconds = microseconds

    @property
    def status_code(self):
        return self._status_code

    @status_code.setter
    def status_code(self,status_code):
        self._status_code = status_code

    @property
    def datalen(self):
        return self._datalen

    @datalen.setter
    def datalen(self,datalen):
        self._datalen = datalen


#http://testuma.babidou.net/api/v1.0/ss-stime
#http://wx.henkuai.com/index.php
class WebPressure(LogParset):
    def __init__(self,website='http://testuma.babidou.net/ssad/whiteList',
                 process=multiprocessing.cpu_count()*2,
                 runcount=100,
                 timeout=3,
                 request_type='get',
                 payload=None,
                 authurl="http://testuma.babidou.net/login",
                 username="admin",
                 passwd="gaopeng"):
        super(WebPressure, self).__init__()
        self.process = process
        self.runcount = runcount
        self.website = website
        self.timeout = timeout
        self.request_type = request_type
        self.payload = payload
        self.authurl = authurl
        self.username = username
        self.passwd = passwd
        self.logdir = "/tmp/"
        self._list = []


    def uuid_2_str(self):
        filename = str(uuid.uuid1())
        return self.logdir + re.sub("-", "", filename)

    def authenticate(self):
        site_request = requests.Session()
        site_request.post(self.authurl, {'username':self.username,'password':self.passwd})
        return site_request

    def request_get(self,_filename,session):
        """每个请求返回结果存储到文件中"""
        try:
            r = session.get(self.website, timeout=self.timeout)
            result = "{microseconds};{status_code};{datalen}\n".\
                format(microseconds=r.elapsed.microseconds,
                       status_code=r.status_code,
                       datalen=len(r.text))
        except:
            result = "0;504;0\n"

        #追加
        with open(_filename,'a') as f:
            f.write(result)

    def request_post(self,_filename,session):
        """每个请求返回结果存储到文件中"""
        try:
            r = session.post(self.website, timeout=self.timeout)
            result = "{microseconds};{status_code};{datalen}\n".\
                format(microseconds=r.elapsed.microseconds,
                       status_code=r.status_code,
                       datalen=len(r.text))
        except:
            result = "0;504;0\n"

        #追加
        with open(_filename,'a') as f:
            f.write(result)

    def coroutine(self,_filename,session):
        """实现协程"""
        if self.request_type == 'get':
            gevent.joinall(
                [gevent.spawn(self.request_get,_filename,session) for i in xrange(self.runcount)]
            )
        elif self.request_type == 'post':
            gevent.joinall(
                [gevent.spawn(self.request_post, _filename,session) for i in xrange(self.runcount)]
            )

    def concurrency(self):
        session = self.authenticate()
        start_time = time.time()
        jobs = []
        for i in xrange(self.process):
            _filename = self.uuid_2_str()
            self._list.append(_filename)
            p = multiprocessing.Process(target=self.coroutine,args=(_filename,session))
            p.start()
            jobs.append(p)
        for job in jobs:
            job.join()
        end_time = time.time()
        return  end_time - start_time

    def statistics(self):
        result_dict = {}
        status_code = {"504":0}
        result_dict['execute_time'] = round(self.concurrency(),2)  #执行总时间
        result_dict['elapsed_time'] = []  # response 总时间(除去504)
        result_dict['data_transferred'] = 0  # 数据总传输(除去504)

        generate = self.log_line_iter(self._list)


        for item in generate:
            if int(item['status_code']) != 504:
                result_dict['elapsed_time'].append(int(item['microseconds']))
                result_dict['data_transferred'] += int(item['datalen'])

            status_code.setdefault(item['status_code'], 0)
            status_code[item['status_code']] += 1



        result_dict['request_sum'] = self.process * self.runcount  # 完成多少次请求
        result_dict['availability'] =  str(round(status_code['200']*100.00/result_dict['request_sum'],2))+"%" # 成功率
        result_dict['status_code'] = status_code
        result_dict['response_time'] = round(result_dict['execute_time']/(result_dict['request_sum']-status_code['504']),5)  # 平均每个请求时间
        result_dict['transaction_rate'] = int((result_dict['request_sum'] - status_code['504'])/result_dict['execute_time'])  # 每秒处理多少次
        result_dict['throughput'] = round(result_dict['data_transferred']/result_dict['execute_time'],2)  # 每秒传输带宽
        result_dict['successful_count'] = status_code['200']  # 成功处理次数
        result_dict['failed_count'] = result_dict['request_sum'] - result_dict['successful_count']  # 失败处理次数
        result_dict['long_time'] = max(result_dict['elapsed_time'])  # 耗时最大
        result_dict['short_time'] = min(result_dict['elapsed_time'])  # 耗时最小

        del result_dict['elapsed_time']

        for item in self._list:
            os.remove(item)

        print "process :" + str(self.process)
        print "count :" + str(self.runcount)

        for key,value in result_dict.iteritems():
            print key+":"+str(value)


if __name__ == '__main__':
     WebPressure().statistics()
    # WebPressure().authenticate()


