# -*- coding: utf-8 -*-
from __future__ import annotations
from functools import wraps
import subprocess
import os
from sqlalchemy.exc import IntegrityError
from flask import *
from sympy.physics.units import amount
from werkzeug.utils import secure_filename
import uuid
import socket
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, session, flash, jsonify
from flask_login import LoginManager, login_required, current_user, login_user, UserMixin, logout_user
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy.exc import SQLAlchemyError
import pytz
from typing import List
from sqlalchemy import Column
from sqlalchemy import Table
from sqlalchemy import ForeignKey
import os
from werkzeug.utils import secure_filename
import pandas as pd
from spire.pdf.common import *
from spire.pdf import *
import json
import markdown

hostname = socket.gethostname()
ip_address = socket.gethostbyname(hostname)
colored_tag_lst = ['technology', 'biology', 'chemistry', 'math', 'physics', 'coding', 'AP', 'bounty']

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'secretkey'

db = SQLAlchemy(app)

# 设置文件上传保存路径
ALLOWED_EXTENSIONS = set(['pdf'])
app.config['UPLOAD_FOLDER'] = 'static/articles/'
# MAX_CONTENT_LENGTH设置上传文件的大小，单位字节
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

UPLOAD_FOLDER = os.path.join('static', 'bounty_images')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def save_bounty_image(file):
    filename = secure_filename(file.filename)
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)
    return '/' + path.replace('\\', '/')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 获取北京时间（UTC+8）
beijing_tz = pytz.timezone('Asia/Shanghai')

# User 类
class User(UserMixin, db.Model):
    __tablename__ = 'User_table'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    realname = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    balance = db.Column(db.Integer, default=0)  # 荣誉货币余额
    is_admin = db.Column(db.Boolean, default=False)  # 是否为管理员
    date_created = db.Column(db.DateTime, default=lambda: datetime.now(beijing_tz))
    # 一个用户可以拥有多篇文章
    articles_users = db.relationship("Article", back_populates="users")

    @property
    def article_count(self):
        return self.articles_users.filter_by(status='published').count()
    
    def __repr__(self):
        return f'<User {self.username}>'

# 中间表：文章与标签的关系
association_table = db.Table('association_table',
    db.metadata,
    db.Column("articles_id", db.Integer, ForeignKey("Article_table.id"), primary_key=True),
    db.Column("tags_id", db.Integer, ForeignKey("Tag_table.id"), primary_key=True)
)

# 多对多关联表：bounty 与 tag 的关系
bounty_tag = db.Table('bounty_tag',
    db.metadata,
    db.Column('bounty_id', db.Integer, db.ForeignKey('Bounty_table.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('Tag_table.id'), primary_key=True)
)

# 悬赏类
class Bounty(db.Model):
    __tablename__ = 'Bounty_table'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)  # 文章要求的固定标题
    description = db.Column(db.Text, nullable=False)  # 问题描述
    reward = db.Column(db.Integer, nullable=False, default=5)  # 荣誉货币奖励
    status = db.Column(db.String(20), default='active')  # active / closed
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(beijing_tz))
    image_path = db.Column(db.String(300), nullable=False)  # 新增：图片路径
    tags = db.relationship('Tag', secondary=bounty_tag, back_populates='bounties')  # 关联标签

# Tag 类
class Tag(db.Model):
    __tablename__ = "Tag_table"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    articles = db.relationship("Article", secondary=association_table, back_populates="tags")
    bounties = db.relationship('Bounty', secondary=bounty_tag, back_populates='tags')

    @property
    def article_count(self):
        return sum(1 for article in self.articles if article.status == 'published')

    def __repr__(self):
        return f'<Tag {self.name}>'

# Article 类
class Article(db.Model):
    __tablename__ = 'Article_table'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    content_path = db.Column(db.String(300), nullable=False)  # 存储 HTML 文件的路径
    status = db.Column(db.String(20), default='draft')  # draft, published, deleted
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(beijing_tz))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(beijing_tz))
    description = db.Column(db.String(500), nullable=False)
    views = db.Column(db.Integer, default=0)
    balance = db.Column(db.Integer, default=0)  # 荣誉货币，默认 0，最大 10
    user_id = db.Column(db.Integer, ForeignKey("User_table.id"))
    users = db.relationship("User", back_populates="articles_users")
    # 文章与标签是多对多的关系
    tags = db.relationship("Tag", secondary=association_table, back_populates="articles")

    def __repr__(self):
        return f'<Article {self.title}>'
    
def modify(str):
    a = str.find("<body style='margin:0'>")
    str = "{% extends 'base_read.html' %}\n{% block content %}\n<div class='left-right-content'>\n<div></div>\n<div class='center-content'>" + str[a+23:]
    a = str.find("</html>")
    str = str[:a - 9] + "</div></div>\n{% endblock %}"
    return str

def check_file_exists(file_path):
    return os.path.exists(file_path)

def PDF2HTML(pdf_pathway, html_pathway):
    if check_file_exists(pdf_pathway):
        doc = PdfDocument()
        doc.LoadFromFile(pdf_pathway)
        convertOptions = doc.ConvertOptions
        convertOptions.SetPdfToHtmlOptions(True, True, 1, True)
        try:
            doc.SaveToFile(html_pathway, FileFormat.HTML)
        except Exception as e:
            return e
        doc.Dispose()

        with open(html_pathway, 'r', encoding='utf-8') as file:
            html_content = file.read()
        processed_html_content = html_content
        a = processed_html_content.find('<g>\n\t\t\t<text style="fill:#FF0000')
        while a != -1:
            replace_content = processed_html_content[a:a+235]
            processed_html_content = processed_html_content.replace(replace_content, "")
            a = processed_html_content.find('<g>\n\t\t\t<text style="fill:#FF0000')

        a = processed_html_content.find('width="793" height="1121"')
        while a != -1:
            replace_content = processed_html_content[a:a + 25]
            processed_html_content = processed_html_content.replace(replace_content, ' viewBox="0 0 793 1121" ')
            a = processed_html_content.find('width="793" height="1121"')
            
        processed_html_content = modify(processed_html_content)
        
        # print(f"===============HTML_PATHWAY{html_pathway}==================")
        with open(html_pathway, 'w', encoding='utf-8') as file:
            file.write(processed_html_content)
        file.close()
        # print("==============Success===============")
        return "Success!"

    else:
        return "File Not Found"
    
def compile_file():
    pathway = str(os.getcwd().replace("\\", "/").lower()) + "/static/articles/"
    hpathway = str(os.getcwd().replace("\\", "/").lower()) + "/templates/articles/"

    for filename in os.listdir(pathway):
        # print(f"============{filename}================")
        if (not filename.startswith("114514")) and (filename.endswith('.pdf')):
            pdf_pathway = pathway + '' + filename
            html_pathway = hpathway + '' + filename[:-4] + ".html"
            print(PDF2HTML(pdf_pathway, html_pathway))
            os.rename(pathway + filename, pathway + "114514" + filename)
        else:
            pass

def import_users_from_excel(excel_path):
    # 读取 Excel 数据（假设工作表为第一个）
    df = pd.read_excel(excel_path)

    beijing_tz = pytz.timezone('Asia/Shanghai')

    # 构造用户列表
    users = []
    for index, row in df.iterrows():
        # 请确保 Excel 文件中有这些列，若没有可以做适当调整
        user = User(
            username=row['username'],
            realname=row['realname'],
            password=row['password'],  # 注意：生产环境不要明文存储密码
            email=row['email'],
            balance=int(row.get('balance', 0)),  # 如果不存在balance，则默认为0
            is_admin=bool(row.get('is_admin', False)),
            date_created=datetime.now(beijing_tz)
        )
        users.append(user)

    try:
        db.session.bulk_save_objects(users)  # 批量保存
        db.session.commit()
        print(f"成功导入 {len(users)} 个用户")
    except Exception as e:
        db.session.rollback()
        print("导入数据时出错：", e)

def update_articles_updated_at(article_ids: list[int]) -> None:
    current_time = datetime.now(beijing_tz)  # 当前北京时间
    # 通过过滤查询所有匹配的文章
    articles = Article.query.filter(Article.id.in_(article_ids)).all()
    for article in articles:
        article.updated_at = current_time
    db.session.commit()
    
# 创建表
with app.app_context():
    db.create_all()
    # import_users_from_excel('old_users.xlsx')
    # update_articles_updated_at([1, 3, 4, 8, 10, 16])

migrate = Migrate(app, db)

def decode(str):
    dictionary = {}
    lstt = str.split('\n')
    for item in lstt:
        idx = item.find(':')
        name = item[:idx]
        value = item[idx+2:]
        dictionary[name] = value
    return dictionary

def visit_doc(file_path, mode='add', para=None, value=None):
    with open(file_path, 'r', encoding='utf-8') as f:
        config = f.read()
    f.close()
    configs = decode(config)

    if (mode == 'params'):
        if (para == None):
            return configs
        else:
            return configs[para]
    elif ((mode == 'add') and ((para != None) and (value != None))):
        configs[para] = str(int(float(configs[para]) + float(value)))
    elif ((mode == 'set') and ((para != None) and (value != None))):
        configs[para] = value

    with open(file_path, 'w', encoding='utf-8') as f:
        for x in configs:
            f.writelines(str(x) + ": " + str(configs[x]) + '\n')
    f.close()

    return configs

login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def check_user(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("请先登录才能访问此页面！", "info")
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def check_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash("你没有足够的权限访问此页面！", "error")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# tag_translations.py
TAG_TRANSLATIONS = {
    'biology': '生物',
    'chemistry': '化学',
    'physics': '物理',
    'math': '数学',
    'technology': '技术',
    'coding': '编程',
    'AP': 'AP',
    'bounty': "🔥悬赏问题"
    # … 其他标签 …
}

@app.template_filter('translate_tag')
def translate_tag(tag_name: str) -> str:
    """将英文标签名转换为中文显示，如果不存在映射，则原样返回英文。"""
    return TAG_TRANSLATIONS.get(tag_name, tag_name)

# 定义存储访问数据的文件路径
VIEW_FILE = "views.json"

# 启动时确保文件存在
def ensure_view_file():
    if not os.path.exists(VIEW_FILE):
        with open(VIEW_FILE, "w") as f:
            json.dump({}, f)

# 调用一次，通常放在 app 初始化阶段
ensure_view_file()

# 更新某个页面访问量
def update_view_count(endpoint):
    # 读取数据
    try:
        with open(VIEW_FILE, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    # 更新计数
    data[endpoint] = data.get(endpoint, 0) + 1

    # 写入文件
    with open(VIEW_FILE, "w") as f:
        json.dump(data, f, indent=2)

@app.after_request
def count_views(response):
    endpoint = request.endpoint
    if endpoint:
        update_view_count(endpoint)
    return response

#==========环境设置====================环境设置====================环境设置====================环境设置====================环境设置====================环境设置==========

#==========无需登录====================无需登录====================无需登录====================无需登录====================无需登录====================无需登录==========

# 首页
@app.route('/')
def index():
    # 示例数据：最新资源、热门文章、社区动态等数据可根据实际情况查询数据库
    latest_resources = Article.query.filter(Article.status=='published').order_by(Article.updated_at.desc()).limit(6).all()
    community_updates = [
        {"title": "近期研讨会预告", "content": "下周将举办关于CRISPR技术的线上研讨会，欢迎报名参加！"},
        {"title": "户外探险新动态", "content": "BMCA 登山队成功完成最新的高原科考任务。"},
        {"title": "论坛热帖", "content": "如何利用最新算法优化科研项目管理？"}
    ]
    # 热门悬赏：查询状态 active 的悬赏，按创建时间倒序，限制 3 条（可以根据需要调整条件）
    hot_bounties = Bounty.query.filter_by(status='active').order_by(Bounty.created_at.desc()).limit(3).all()
    return render_template('index.html', latest_resources=latest_resources, community_updates=community_updates, hot_bounties=hot_bounties, title="科学资源", colored_tag_lst=colored_tag_lst)

# 注册
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        realname = request.form['realname']
        password = request.form['password']
        email = request.form['email']

        user = User.query.filter_by(email=email).first()
        if user:
            flash('邮箱已被注册！', 'warning')
            return redirect(url_for('register'))

        user = User.query.filter_by(username=username).first()
        if user:
            flash('用户名已经被注册！', 'warning')
            return redirect(url_for('register'))

        new_user = User(
            username=username, email=email, realname=realname, password=password, is_admin=True if ("admin" == username) else False
        )
        db.session.add(new_user)
        db.session.commit()

        flash('注册成功，请登录！', 'success')
        return redirect(url_for('login'))

    return render_template('register.html', title="注册")

# 登录
@app.route('/login', methods=['GET', 'POST'])
def login():
    next_page = request.args.get('next')
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if not user:
            flash('用户不存在！', 'error')
            return redirect(url_for('login'))

        if (user.password != password):
            flash('密码不正确！', 'error')
            return redirect(url_for('login'))

        login_user(user)
        flash('登录成功！', 'success')

        return redirect(next_page if next_page else url_for('dashboard', user_id=current_user.id))

    return render_template('login.html', title="登录", next_page=next_page)

# 阅读文章界面
@app.route('/articles', methods=['GET'])
def view_all_articles():
    query = request.args.get('query', '').strip()
    filter_by = request.args.get('filter', 'title')  # 默认为标题搜索
    file_path = 'config.txt'
    visit_doc(file_path, mode='add', para="views", value=1)

    # 构造查询，仅查询已发布文章
    articles_query = Article.query.filter(Article.status == 'published')
    
    # 如果提供了搜索关键字，根据 filter_by 进行过滤
    if query:
        if filter_by == 'title':
            articles_query = articles_query.filter(Article.title.ilike(f"%{query}%"))
        elif filter_by == 'description':
            articles_query = articles_query.filter(Article.description.ilike(f"%{query}%"))
    
    articles = articles_query.all()
    
    # 传递 query 和 filter 方便前端显示当前选项
    return render_template('all_articles.html', articles=articles, mode='read', colored_tag_lst=colored_tag_lst, query=query, filter=filter_by, title="阅读投稿")

    
    
# 阅读文章路由
@app.route('/view_article/<int:article_id>', methods=['GET', 'POST'])
def view_article(article_id):
    article = Article.query.get_or_404(article_id)
    mode = request.args.get('mode')
    # 从文件中读取 HTML 内容
    article.views += 1
    db.session.commit()
    content_path = article.content_path
    return render_template(content_path, article=article, title=article.title, colored_tag_lst=colored_tag_lst, mode=mode)

# 按标签阅读
@app.route('/manage_tags', methods=['GET', 'POST'])
def manage_tags():
    tags = Tag.query.all()  # 获取所有标签和它们的文章数量
    return render_template('manage_tags.html', tags=tags, title='分类')

# 按标签阅读路由
@app.route('/view_articles_by_tag/<int:tag_id>', methods=['GET'])
def view_articles_by_tag(tag_id):
    tag = Tag.query.get_or_404(tag_id)
    articles = tag.articles  # 获取该标签下的所有文章
    return render_template('view_articles_by_tag.html', tag=tag, articles=articles, title=f'标签 {TAG_TRANSLATIONS.get(tag.name, tag.name)} 下的文章')

# 关于我们
@app.route('/about')
def about():
    return render_template('about.html', title="关于我们")

# 网站教程界面
@app.route('/tutorial')
def tutorial():
    return render_template('tutorial.html', title="网站使用教程")

#==========无需登录====================无需登录====================无需登录====================无需登录====================无需登录====================无需登录==========

#==========需要登录====================需要登录====================需要登录====================需要登录====================需要登录====================需要登录==========

@app.route('/bounties')
@check_user
def bounties():
    if current_user.is_admin:
        # 管理员可见所有悬赏
        bounties = Bounty.query.order_by(Bounty.created_at.desc()).all()
    else:
        # 普通用户只见 active=True 的悬赏
        bounties = Bounty.query.filter_by(status='active').order_by(Bounty.created_at.desc()).all()

    return render_template('bounties.html', bounties=bounties, colored_tag_lst=colored_tag_lst, title="热门悬赏")


# 上传文章
@app.route('/upload', methods=['GET', 'POST'])
@check_user
def upload():
    article_id = request.args.get('article_id')  # 获取文章 ID（编辑模式）
    bounty_id = request.args.get('bounty_id', type=int)

    if request.method == 'GET':
        tags = Tag.query.all()  # 获取所有标签
        article = None
        bounty = None
        
        if bounty_id:
            bounty = Bounty.query.get_or_404(bounty_id)

        if article_id:
            article = Article.query.get(article_id)
            if (not article) or (article.user_id != current_user.id):
                flash("文章不存在或你无权编辑！", "error")
                return redirect(url_for('index'))
        
        return render_template('upload.html', 
                               tags=tags, 
                               title='回答悬赏' if bounty_id else ('编辑文章' if article_id else '创建文章'),
                               article=article,
                               bounty=bounty)

    else:
        title = request.form['title']
        description = request.form['description']
        selected_tags = request.form.get('tags')
        selected_tags = selected_tags.split(',') if selected_tags else []
        file = request.files.get('file')

        if article_id:  # 编辑文章模式
            article = Article.query.get(article_id)
            if (not article) or (article.user_id != current_user.id):
                flash("文章不存在或你无权编辑！", "error")
                return redirect(url_for('index'))
            
            if file and file.filename:
                if not allowed_file(file.filename):
                    flash("错误文件类型！请上传 .pdf 格式", 'error')
                    return redirect(url_for('upload', article_id=article_id))
                
                os.remove('static/articles/114514' + article.title + '.pdf')
                os.remove('templates/articles/' + article.title + '.html')
            
                article.title = title
                article.description = description
                article.updated_at = datetime.now(beijing_tz)  # 更新时间戳

                file.save("static/articles/" + title + '.pdf')
                article.content_path = "/articles/" + title + '.html'
                
                compile_file()
                
                # 更新标签
                article.tags.clear()
                for tag_id in selected_tags:
                    tag = Tag.query.get(tag_id)
                    if tag:
                        article.tags.append(tag)

                db.session.commit()
                flash('文章更新成功！', 'success')
        else:  # 创建文章模式
            if not allowed_file(file.filename):
                flash("错误文件类型！请上传 .pdf 格式", 'error')
                return redirect(url_for('upload'))

            if Article.query.filter_by(title=title).first():
                flash('不要重复上传已有内容！请上传新内容', 'error')
                return redirect(url_for('upload'))

            file.save("static/articles/" + title + '.pdf')
            file_path = "/articles/" + title + '.html'

            compile_file()

            article = Article(
                title=title,
                description=description,
                content_path=file_path,
                user_id=current_user.id
            )

            for tag_id in selected_tags:
                tag = Tag.query.get(tag_id)
                article.tags.append(tag)

            db.session.add(article)
            db.session.commit()
            flash('文章创建成功！', 'success')

        return redirect(url_for('view_article', article_id=article.id))

# 修改文章
@app.route('/modify_article/<int:article_id>', methods=['GET', 'POST'])
@check_user
def modify_article(article_id):
    article = Article.query.get_or_404(article_id)
    if article.user_id != current_user.id:
        flash("你没有权限修改这篇文章", "danger")
        return redirect(url_for('view_all_articles'))
    
    article.status = 'draft'
    db.session.commit()
    
    flash("文章已设置为草稿状态，请进行重新编辑", "success")
    return redirect(url_for('upload', article_id=article.id))

# 登出
@app.route('/logout')
@check_user
def logout():
    logout_user()
    flash('成功登出', 'success')
    return redirect('/')

# 个人主页
@app.route('/dashboard/<int:user_id>')
@check_user
def dashboard(user_id):
    user = User.query.get_or_404(user_id)
    articles = user.articles_users
    return render_template('dashboard.html', user=user, title="个人面板", colored_tag_lst=colored_tag_lst, articles=articles)

# 销户
@app.route('/delete-account', methods=['GET', 'POST'])
@check_user
def delete_account():
    if request.method == 'POST':
        user = current_user
        db.session.delete(user)  # 从数据库中删除用户
        db.session.commit()
        logout_user()
        flash('您的账户已成功删除。', 'success')
        return redirect(url_for('index'))

    return render_template('delete_account.html', title="确认注销")

#==========需要登录====================需要登录====================需要登录====================需要登录====================需要登录====================需要登录==========

#==========仅管理员====================仅管理员====================仅管理员====================仅管理员====================仅管理员====================仅管理员==========

@app.route('/create_bounty', methods=['GET', 'POST'])
@check_admin
def create_bounty():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        reward = request.form['reward']
        selected_tags = request.form.getlist('tags')[0].split(',')  # 获取选中的标签ID
        image = request.files.get('image')

        print(image)

        new_bounty = Bounty(
            title=title,
            description=description,
            reward=reward,
            status='active',  # 默认状态为active
            tags=[Tag.query.get(tag_id) for tag_id in selected_tags]
        )
        
        if image and image.filename:
            new_bounty.image_path = save_bounty_image(image)
        
        db.session.add(new_bounty)
        db.session.commit()
        flash(f'悬赏问题 {new_bounty.title} 创建成功！', 'success')
        
        return redirect(url_for('bounties'))  # 成功后跳转到后台管理页面

    # GET请求，渲染创建悬赏问题的表单页面
    tags = Tag.query.all()
    return render_template('create_bounties.html', tags=tags, is_edit=False, colored_tag_lst=colored_tag_lst, title='创建悬赏问题')

@app.route('/edit_bounty/<int:bounty_id>', methods=['GET', 'POST'])
@check_admin
def edit_bounty(bounty_id):
    bounty = Bounty.query.get_or_404(bounty_id)
    
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        reward = request.form['reward']
        selected_tags = request.form.getlist('tags')[0].split(',')  # 获取选中的标签ID
        image = request.files.get('image')

        if image and image.filename:
            bounty.image_path = save_bounty_image(image)
        
        bounty.title = title
        bounty.description = description
        bounty.reward = reward
        bounty.tags = [Tag.query.get(tag_id) for tag_id in selected_tags]
        db.session.commit()
        flash(f'悬赏问题 {bounty.title} 更新成功！', 'success')
        
        return redirect(url_for('bounties'))  # 成功后跳转到后台管理页面

    # GET请求，渲染编辑悬赏问题的表单页面
    tags = Tag.query.all()
    return render_template('create_bounties.html', bounty=bounty, tags=tags, is_edit=True, colored_tag_lst=colored_tag_lst, title="编辑悬赏问题")

@app.route('/delete_bounty/<int:bounty_id>', methods=['POST'])
@check_admin
def delete_bounty(bounty_id):
    bounty = Bounty.query.get_or_404(bounty_id)
    
    # 删除悬赏问题
    db.session.delete(bounty)
    db.session.commit()

    flash(f'悬赏问题 {bounty.title} 已删除', 'success')
    return redirect(url_for('bounties'))  # 删除成功后跳转到后台管理页面


# 用户表界面 (仅管理员)
@app.route('/admin')
@check_admin
def admin():
    sort_by = request.args.get('sort_by', 'id')
    order = request.args.get('order', 'asc')
    
    valid_columns = {'id', 'username', 'realname', 'email', 'password', 'balance', 'article_count', 'is_admin'}
    if sort_by not in valid_columns:
        sort_by = 'id'
    
    # 过滤掉管理员用户
    query = User.query.filter(User.username != 'admin') \
            .outerjoin(Article) \
            .group_by(User.id) \
            .with_entities(
                User.id,
                User.username,
                User.realname,
                User.email,
                User.password,
                User.balance,
                User.is_admin,
                db.func.count(Article.id).label('article_count')
            )
    
    if sort_by == 'article_count':
        if order == 'desc':
            query = query.order_by(db.desc('article_count'))
        else:
            query = query.order_by('article_count')
    else:
        column_attr = getattr(User, sort_by)
        if order == 'desc':
            query = query.order_by(db.desc(column_attr))
        else:
            query = query.order_by(column_attr)
    
    users = query.all()
    return render_template('admin.html', users=users, sort_by=sort_by, order=order, title="管理员")


# 转移荣誉货币 (仅管理员)
@app.route('/transfer', methods=['POST'])
@check_admin
def transfer():
    sender = current_user
    recipient_username = request.form['recipient']
    amount = int(round(float(request.form['amount'])))

    recipient = User.query.filter_by(username=recipient_username).first()
    if not recipient:
        flash('该用户不存在', 'error')
    elif sender.balance < amount:
        flash('余额不足', 'error')
    else:
        sender.balance -= amount
        recipient.balance += amount
        db.session.commit()
        file_path = 'config.txt'
        visit_doc(file_path, mode='add', para='coin_trsf', value=amount)
    return redirect(url_for('dashboard', user_id=current_user.id))

# 交接管理员权限 (仅管理员)
@app.route('/toggle-admin/<int:user_id>', methods=['POST'])
@check_admin
def toggle_admin(user_id):
    user = User.query.get(user_id)
    if user:
        flash(f'成功{"取消" if user.is_admin else "设置"} {user.username} 为管理员。', 'warning')
        user.is_admin = not user.is_admin  # 切换管理员状态
        db.session.commit()
        return redirect(url_for('dashboard', user_id=current_user.id))
    else:
        flash('用户未找到！', 'error')

    return redirect(url_for('admin'))

# 审核文章界面 (仅管理员)
@app.route('/audit_articles', methods=['GET', 'POST'])
@check_admin
def audit_articles():
    if not current_user.is_admin:
        flash('You have no permission to this page!', 'danger')
        return redirect(url_for('index'))
    
    query = request.args.get('query', '').strip()
    filter_by = request.args.get('filter', 'title')  # 默认为标题搜索
    file_path = 'config.txt'
    visit_doc(file_path, mode='add', para="views", value=1)

    # 构造查询，仅查询已发布文章
    articles_query = Article.query.filter(Article.status == 'draft')
    
    # 如果提供了搜索关键字，根据 filter_by 进行过滤
    if query:
        if filter_by == 'title':
            articles_query = articles_query.filter(Article.title.ilike(f"%{query}%"))
        elif filter_by == 'description':
            articles_query = articles_query.filter(Article.description.ilike(f"%{query}%"))
    
    articles = articles_query.all()
    
    # 传递 query 和 filter 方便前端显示当前选项
    return render_template('all_articles.html', articles=articles, mode='audit', colored_tag_lst=colored_tag_lst, query=query, filter=filter_by, title="审核投稿")


# 审核文章路由 (仅管理员)
@app.route('/audit_article/<int:article_id>', methods=['POST'])
@check_admin
def audit_article(article_id):
    article = Article.query.get_or_404(article_id)
    author = article.users # 获取文章作者
    decision = request.form.get('decision')  # 获取审核决定
    requested_honor = int(request.form.get('honorCurrency', 0))  # 获取荣誉货币（默认为0）

    if decision == "approve":
        # 计算实际可增加的荣誉货币（不超过10）
        max_addable = 10 - article.balance
        actual_honor = min(requested_honor, max_addable)
        # print(requested_honor)

        if (actual_honor > 0) or (requested_honor == 0):
            article.balance += actual_honor
            article.status = 'published'
            author.balance += actual_honor
            flash(f"审核通过！授予 {author.username} 用户的 {article.title} 文章 {actual_honor} 个荣誉货币。", "success")
        else:
            article.status = 'published'
            flash(f"审核通过，但 {author.username} 用户的 {article.title} 文章已达荣誉货币上限（10）。", "success")

    elif decision == "reject":
        article.status = 'deleted'
        flash("审核拒绝，{author.username} 用户的 {article.title} 文章 未通过。", "error")

    db.session.commit()
    return redirect(url_for('view_all_articles'))  # 返回文章列表

# 删除文章 (仅管理员)
@app.route('/delete_article/<int:article_id>', methods=['POST'])
@check_admin
def delete_article(article_id):
    article = Article.query.get_or_404(article_id)
    if article.status == 'draft':
        os.remove('static/articles/' + article.title + '.pdf')
    elif article.status == 'published':
        os.remove('static/articles/114514' + article.title + '.pdf')
    os.remove('templates/articles/' + article.title + '.html')
    article.status = 'deleted'
    db.session.delete(article)
    db.session.commit()
    flash("Article deleted successfully.", "success")
    return redirect(url_for('view_all_articles'))

# 创建标签 (仅管理员)
@app.route('/create_tag', methods=['POST'])
@check_admin
def create_tag():
    tag_name = request.form['tag_name'].strip()
    if not tag_name:
        return jsonify({"success": False, "message": "标签名称不能为空！"})

    tag = Tag.query.filter_by(name=tag_name).first()
    if tag:
        return jsonify({"success": False, "message": f'标签"{tag_name}"已存在！'})

    new_tag = Tag(name=tag_name)
    db.session.add(new_tag)
    db.session.commit()

    return jsonify({"success": True, 'message': f'标签"{tag_name}"创建成功！'})

# 删除标签 (仅管理员)
@app.route('/delete_tag/<int:tag_id>', methods=['DELETE'])
@check_admin
def delete_tag(tag_id):
    tag = Tag.query.get(tag_id)
    if tag:
        db.session.delete(tag)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False})

# 取消一个文章的标签路由 (仅管理员)
@app.route('/remove_tag_from_article/<int:article_id>/<int:tag_id>', methods=['DELETE'])
@check_admin
def remove_tag_from_article(article_id, tag_id):
    article = Article.query.get_or_404(article_id)
    tag = Tag.query.get_or_404(tag_id)

    if tag in article.tags:
        article.tags.remove(tag)
        db.session.commit()  # 提交更改
        return jsonify({'success': True})

    return jsonify({'success': False, 'message': 'Tag not associated with article'})

@app.route('/increase_balance', methods=['POST'])
@check_admin
def increase_balance():
    user_id = request.form.get('user_id', type=int)
    amount = request.form.get('amount', type=int)
    if (not user_id or 
    not amount or 
    amount < -100 or 
    amount > 100 or 
    (amount < 0 and current_user.balance < abs(amount))):
        flash("无效的参数！", "error")
        return redirect(url_for('dashboard', user_id=user_id if user_id else current_user.id))
    
    user = User.query.get(user_id)
    if not user:
        flash("用户不存在！", "error")
        return redirect(url_for('dashboard', user_id=current_user.id))
    
    user.balance += amount
    db.session.commit()
    flash(f"成功增加 {amount} 荣誉货币！", "success")
    return redirect(url_for('dashboard', user_id=user.id))


#==========仅管理员====================仅管理员====================仅管理员====================仅管理员====================仅管理员====================仅管理员==========

if __name__ == '__main__':
    app.run(host=ip_address,port=8889, debug=True)
