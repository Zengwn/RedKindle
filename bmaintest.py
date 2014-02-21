#!/usr/bin/env python
# -*- coding:utf-8 -*-

__Version__ = "1.0"
__Author__ = "ynhacler"


import os, datetime, logging, __builtin__, hashlib, time
from collections import OrderedDict, defaultdict
import gettext



# for debug
log = logging.getLogger()
__builtin__.__dict__['default_log'] = log

import web
import jinja2
from bs4 import BeautifulSoup
import model

from config import *

#设置编码方式
import sys
reload(sys)
sys.setdefaultencoding('utf8')


#调试模式
#session不能工作在debug模式
web.config.debug = False


#from books import BookClasses, BookClass
from books.base import BaseFeedBook,  BaseUrlBook

#使用rq任务队列
from rq2 import Queue,use_connection
from worker import conn
from pushworker import pushwork

def local_time(fmt="%Y-%m-%d %H:%M", tz=TIMEZONE):
	return (datetime.datetime.utcnow()+datetime.timedelta(hours=tz)).strftime(fmt)

def hide_email(email):
	""" 隐藏真实email地址，使用星号代替部分字符，适用于4位字符以上 """
	email = email.split('@')
	to = email[0][0:2] + ''.join(['*' for s in email[0][2:-1]]) + email[0][-1]
	return to + '@' + email[-1]

def set_lang(lang):
	""" 设置网页显示语言 """
	tr = gettext.translation('lang', 'i18n', languages=[lang])
	tr.install(True)
	jjenv.install_gettext_translations(tr)

#基础类
class BaseHandler:
	@classmethod
	def logined(self):
		return True if session.login == 1 else False

	#检查session是否登录
	def login_required(self, username=None):
		if (session.login == 0) or (username and username != session.username):
			raise web.seeother(r'/')

	#检查是否有此用户
	def getcurrentuser(self):
		self.login_required()
		u = model.getuser(session.username)
		if not u:
			raise web.seeother(r'/')
		return u[0]




#主页
class Home(BaseHandler):
	def GET(self):
		return jjenv.get_template('home.html').render(nickname=session.username,title="Home")

#登录
class Login(BaseHandler):
	def GET(self):
		tips = "请输入邮箱地址和密码。"

		if session.login == 1:#是否登录
			web.seeother(r'/')
		else:
			return jjenv.get_template("login.html").render(nickname='',title='Login',tips=tips)

	def POST(self):
		name, passwd = web.input().get('u'), web.input().get('p')
		if name.strip() == '':
			tips = "地址为空！"
			return jjenv.get_template("login.html").render(nickname='',title='Login',tips=tips)
		elif len(name) > 35:
			tips = "地址过长!"
			return jjenv.get_template("login.html").render(nickname='',title='Login',tips=tips,username=name)
		elif '<' in name or '>' in name or '&' in name:
			tips = "包含非法字符!"
			return jjenv.get_template("login.html").render(nickname='',title='Login',tips=tips)
		pwdhash = hashlib.md5(passwd).hexdigest()
		if model.isuser(name,pwdhash) == 1:
			session.login = 1
			session.username = name
			raise web.seeother(r'/')
		else:
			tips = "帐号不存在或密码错误!"
			session.login = 0
			session.username = ''
			return jjenv.get_template("login.html").render(nickname='',title='Login',tips=tips,username=name)

#退出登录
class Logout(BaseHandler):
	def GET(self):
		session.login = 0
		session.username = ''
		session.kill()
		raise web.seeother(r'/')

#管理我的订阅和杂志列表
class MySubscription(BaseHandler):
	def GET(self,tips=None):
		user = self.getcurrentuser()
		#所有RSS源和已订阅的源
		ownfeeds = model.userid2feeds(user.k_id) if user else None
		books = list(model.get_allbooks())#webpy返回的是storage对象，用一次就不见了
		return jjenv.get_template("my.html").render(nickname=session.username,current='my',title='My subscription',books=books,ownfeeds=ownfeeds,tips=tips,level=user.level)

	def POST(self):#添加自定义RSS
		user = self.getcurrentuser()
		title = web.input().get('t')
		url = web.input().get('url')
		isfulltext = int(bool(web.input().get('full')))
		if not title or not url:
			return self.GET('title or url is empty!')
		#添加
		model.put_feed(title,url,isfulltext)
		raise web.seeother('/my')

#订阅
class Subscribe(BaseHandler):
	def GET(self, id):
		self.login_required()
		if not id:
			return "the id is empty!<br />"
		try:
			id = int(id)
		except:
			return "the id is invalid!<br />"
		#判断书id是否正确
		b = model.ifhasbook(id)
		if b == 0:
			return "the book(%d) not exist!<br />" % id


		#订阅(判断是否已经订阅)
		user = self.getcurrentuser()
		model.put_subscribe(user.k_id,id)

		raise web.seeother('/my')

#取消订阅
class Unsubscribe(BaseHandler):
	def GET(self, id):
		self.login_required()
		if not id:
			return "the id is empty!<br />"
		try:
			id = int(id)
		except:
			return "the id is invalid!<br />"

		#判断书id是否正确
		b = model.ifhasbook(id)
		if b == 0:
			return "the book(%d) not exist!<br />" % id


		#取消订阅(判断是否已经订阅)
		user = self.getcurrentuser()
		model.put_unsubscribe(user.k_id,id)

		raise web.seeother('/my')

#管理员删除feed
class Deletefeed(BaseHandler):
	def GET(self,id):
		self.login_required()
		if not id:
			return "the id is empty!<br/>"
		try:
			id = int(id)
		except:
			return "the id is invalid!<br/>"

		#判断书id是否正确
		b = model.ifhasbook(id)
                if b == 0:
			return "the book(%d) not exist!<br />" % id

		model.delete_feed(id)

		raise web.seeother('/my')


#设置页面
class Setting(BaseHandler):
	def GET(self, success=False):
		user = self.getcurrentuser()
		return jjenv.get_template('setting.html').render(nickname=session.username,title="Setting",current='setting',user=user,mail_sender=SrcEmail,success=success)

	def POST(self):
		user = self.getcurrentuser()
		kindle_email = web.input().get('kindle_email')
		timezone = int(web.input().get('timezone'))
		send_time = (web.input().get('send_time'))
		enable_send = int(bool(web.input().get('enable_send')))
		keep_image = int(bool(web.input().get("keepimage")))

		#用户信息设置
		model.put_user_messgaes(user.k_id,kindle_email,send_time,enable_send,keep_image,timezone)
		'''
		print kindle_email
		print send_time
		print enable_send
		print keep_image
		print timezone
		'''
		raise web.seeother('')#刷新

#注册
class Register(BaseHandler):
	def GET(self):
		if session.login == 1:#是否登录
			web.seeother(r'/')
		else:
			return jjenv.get_template("register.html").render(nickname='',title='Register')


	def POST(self):
		name = web.input().get('u')
		passwd = web.input().get('p')

		#检查是否已存在，格式问题
		if name.strip() == '' or passwd.strip() == '':
			tips = "不能为空!"
			return jjenv.get_template("register.html").render(nickname='',title='Register',tips=tips)
		elif len(name) > 35:
			tips = "地址太长!"
			return jjenv.get_template("register.html").render(nickname='',title='Register',tips=tips,username=name)
		elif '<' in name or '>' in name or '&' in name:
			tips = "含有非法字符!"
			return jjenv.get_template("register.html").render(nickname='',title='Register',tips=tips)

		u = model.getuser(name)
		if u:
			return jjenv.get_template("register.html").render(nickname='',title='Register',tips="用户已存在!")
		#注册
		model.input_user(name,hashlib.md5(passwd).hexdigest())

		#返回登录界面
		raise web.seeother(r'/')

#推送
class Deliver(BaseHandler):
	def GET(self):
		username = web.input().get('u')
		if username:
			#搜索自动处理的feed(字符串http开头)
			feeds = []
			#搜索手动处理的feed
			mfeeds = []
			ownfeeds = model.username2feeds(username)
			if len(ownfeeds) != 0:
				#取feeds信息
				books = (model.get_allbooks())
				for book in books:
					if book.f_id in ownfeeds:
						b=[]
						if cmp('http',book.url[0:4].lower()) == 0:
							b.append(book.title)
							b.append(book.url)
							if book.isfulltext == 1:
								b.append(True)
							else:
								b.append(False)
							feeds.append(b)
						else:
							b.append(book.url)
							mfeeds.append(b)
				#取用户信息
				user = model.getuser(username)[0]
				#加入eq
				if user and user.kindle_email:
					jobq.enqueue(pushwork,user.kindle_email,feeds,mfeeds,user.keep_image)
			return jjenv.get_template("autoback.html").render(nickname=session.username,title='Delivering',tips='books put to queue!')

#=====================================================
urls = (
	r"/", "Home",
	"/login","Login",
	"/logout", "Logout",
	"/my", "MySubscription",
	"/subscribe/(.*)", "Subscribe",
	"/unsubscribe/(.*)", "Unsubscribe",
	"/setting", "Setting",
	"/deliver", "Deliver",
	"/register","Register",
	"/delfeed/(.*)","Deletefeed",
)

app = web.application(urls,globals())

session =  web.session.Session(app, web.session.DiskStore('sessions'),initializer={'username':'','login':0})

jjenv = jinja2.Environment(loader=jinja2.FileSystemLoader('templates_web'),extensions=["jinja2.ext.do",])

use_connection(conn)

jobq = Queue()


if __name__ == "__main__":
	app.run()
else:
	application=app.wsgifunc()
