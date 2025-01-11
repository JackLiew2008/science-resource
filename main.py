# -*- coding: utf-8 -*-
from __future__ import annotations
import subprocess
import os
from sqlalchemy.exc import IntegrityError
from astroquery.ipac.irsa.sha import query
from flask import *
from sympy.physics.units import amount
from werkzeug.utils import secure_filename
import uuid
import socket
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, session, flash, jsonify
from flask_login import LoginManager, login_required, current_user, login_user, UserMixin, logout_user
from flask_mail import Mail, Message
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer, BadSignature, SignatureExpired
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError
import pytz

from typing import List
from sqlalchemy import Column
from sqlalchemy import Table
from sqlalchemy import ForeignKey
import os
from werkzeug.utils import secure_filename

hostname = socket.gethostname()
ip_address = socket.gethostbyname(hostname)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'secretkey'

# 设置文件存储路径
UPLOAD_FOLDER = 'e://flask_project/pythonProject/templates/reads/'
ALLOWED_EXTENSIONS = {'html'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


db = SQLAlchemy(app)

# 设置文件上传保存路径
UPLOAD_FOLDER = 'static/articles/'
ALLOWED_EXTENSIONS = set(['pdf'])
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# MAX_CONTENT_LENGTH设置上传文件的大小，单位字节
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

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

    def __repr__(self):
        return f'<User {self.username}>'

# 中间表：文章与标签的关系
association_table = db.Table(
    'association_table',
    db.metadata,
    db.Column("articles_id", db.Integer, ForeignKey("Article_table.id"), primary_key=True),
    db.Column("tags_id", db.Integer, ForeignKey("Tag_table.id"), primary_key=True)
)

# Tag 类
class Tag(db.Model):
    __tablename__ = "Tag_table"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    # 文章与标签是多对多的关系
    articles = db.relationship("Article", secondary=association_table, back_populates="tags")

    @property
    def article_count(self):
        return len(self.articles)

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
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(beijing_tz), onupdate=lambda: datetime.now(beijing_tz))
    description = db.Column(db.String(500), nullable=False)
    views = db.Column(db.Integer, default=0)
    user_id = db.Column(db.Integer, ForeignKey("User_table.id"))
    users = db.relationship("User", back_populates="articles_users")
    # 文章与标签是多对多的关系
    tags = db.relationship("Tag", secondary=association_table, back_populates="articles")

    def __repr__(self):
        return f'<Article {self.title}>'

# 创建表
with app.app_context():
    db.create_all()

def decode(str):
    dictionary = {}
    lstt = str.split('\n')
    for item in lstt:
        idx = item.find(':')
        #print(item[:idx], item[idx+2:])
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

@login_manager.unauthorized_handler
def unauthorized():
    flash('请先登录才能访问此页面！', 'info')
    return redirect(url_for('login', next=request.url))

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
        print(next_page)
        flash('登录成功！', 'success')
        if next_page:
            redirect_to = next_page
        else:
            redirect_to = url_for('dashboard')

        return redirect(redirect_to)
        #return redirect(next_page or url_for('dashboard'))
        #return redirect(url_for('dashboard'))

    return render_template('login.html', title="登录", next_page=next_page)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('成功登出', 'success')
    return redirect('/')

@app.route('/dashboard')
@login_required
def dashboard():
    print(f"Welcome {current_user.username} to your profile!")
    return render_template('dashboard.html', user=current_user, title="我的金库")

@app.route('/admin')
@login_required
def admin():
    all_users = User.query.all()
    return render_template('admin.html', users=all_users, title="管理员")

@app.route('/transfer', methods=['POST'])
@login_required
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

    return redirect(url_for('dashboard'))

@app.route('/delete-account', methods=['GET', 'POST'])
@login_required
def delete_account():
    if request.method == 'POST':
        user = current_user
        db.session.delete(user)  # 从数据库中删除用户
        db.session.commit()
        logout_user(user)
        flash('您的账户已成功删除。', 'success')
        return redirect(url_for('index'))

    return render_template('delete_account.html', title="确认注销")

@app.route('/toggle-admin/<int:user_id>', methods=['POST'])
@login_required
def toggle_admin(user_id):
    user = User.query.get(user_id)
    if user:
        user.is_admin = not user.is_admin  # 切换管理员状态
        db.session.commit()
        flash(f'成功{"取消" if user.is_admin else "设置"} {user.username} 为管理员。', 'warning')

        return redirect(url_for('dashboard'))
    else:
        flash('用户未找到！', 'error')

    return redirect(url_for('admin'))

@app.route('/get-reads')
def get_reads():
    files = []
    for filename in os.listdir("templates/reads/"):
        if os.path.exists("templates/reads/" + filename + "/preview.txt"):
            with open("templates/reads/" + filename + "/preview.txt", "r", encoding='utf-8') as f:
                content = f.read()
            f.close()
            params = decode(content)
            #print(params)
            files.append({
                "title" : filename,
                "user" : params['user'],
                "view" : params['view'],
                "description" : params['description'],
                "link" : '/file/' + filename
            })

    return jsonify(files)

@app.route('/get-audit')
def get_audit():
    files = []
    for filename in os.listdir("templates/reads/"):
        if os.path.exists("templates/reads/" + filename + "/(undefined)preview.txt"):
            with open("templates/reads/" + filename + "/(undefined)preview.txt", "r", encoding='utf-8') as f:
                content = f.read()
            f.close()
            params = decode(content)
            files.append({
                "title": filename,
                "user": params['user'],
                "description": params['description'],
                "link": '/file/' + filename
            })
    return jsonify(files)

@app.route('/upload2', methods=['GET', 'POST'])
@login_required
def upload2():
    user = current_user
    if (request.method == 'GET'):
        return render_template('upload2.html')

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    # 如果是get请求响应上传视图，post请求响应上传文件
    sender = current_user
    if (request.method == 'GET'):
        return render_template('upload.html', title="上传")
    else:
        error_message = ""
        title = request.form['title']
        description = request.form['description']
        file = request.files['file']

        if not allowed_file(file.filename):
            error_message = "Wrong File Type!"
            instruction = "Upload again with .pdf format"
            #print("hahaha2")
            flash_content = error_message + "" + instruction
            flash(flash_content, 'error')
            return redirect(url_for('upload'))

        elif os.path.exists("templates/reads/" + title):
            error_message = "Seems you are trying to upload a file that already exists!"
            instruction = "Upload a new content with .pdf format"
            #print("hahaha2")
            flash_content = error_message + "" + instruction
            flash(flash_content, 'error')
            return redirect(url_for('upload'))

        else:
            fileName = file.filename
            if not os.path.exists("templates/reads/" + title):
                os.mkdir("templates/reads/" + title)

            file.save("templates/reads/" + title + "/" + fileName)

            with open("templates/reads/" + title + "/(undefined)preview.txt", "w", encoding='utf-8') as f:
                f.writelines("description: " + str(description) + '\n')
                f.writelines("user: " + sender.username + '\n')
                f.writelines("upload_time: " + datetime.now().strftime("%Y:%m:%d-%H:%M:%S") + "\n")
                f.writelines("view: " + str(0) + '\n')
            f.close()

            command = "python " + str(os.getcwd().replace("\\", "/").lower()) + "/execution1.py"
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            print(result.stdout)
            print(result.stderr)

            amount = 1

            sender.balance += amount
            db.session.commit()

            file_path = 'config.txt'
            visit_doc(file_path, mode='add', para='coin_tot', value=amount)

            flash(f"上传成功！获得 {amount} 荣誉货币！", 'success')
            return redirect(url_for('index'))

@app.route('/file/<filename>', methods=['GET'])
def read_file(filename):
    if request.method == "GET":
        #print(0)
        for file in os.listdir("templates/reads/" + filename):
            if (file.endswith(".txt")):
                #print(1)
                file_path = "templates/reads/" + filename + "/" + file
                params = visit_doc(file_path, mode='add', para="view", value=1)

        for file in os.listdir("templates/reads/" + filename):
            if (file.endswith(".html")):
                #print(2)
                return render_template("/reads/" + filename + "/" + file, title=filename, state="reads")

@app.route('/audit_file/<filename>', methods=['GET'])
@login_required
def audit_file(filename):
    if request.method == "GET":
        for file in os.listdir("templates/reads/" + filename):
            if (file.endswith(".txt")):

                file_path = "templates/reads/" + filename + '/' + file
                params = visit_doc(file_path, mode='add', para="view", value=0)

        for file in os.listdir("templates/reads/" + filename):
            if (file.endswith(".html")):
                return render_template("/reads/" + filename + "/" + file, username=params['user'], title=filename, state="audit", filename=filename)

@app.route('/audit_move/<filename>', methods=['GET', 'POST'])
@login_required
def audit_move(filename):
    for file in os.listdir("templates/reads/" + filename):
        if (file.endswith(".txt")):

            file_path = "templates/reads/" + filename + '/' + file
            params = visit_doc(file_path, mode='params')

    username = params['user']
    sender = User.query.filter_by(username=username).first()
    amount = int(float(request.form['honorCurrency']))


    sender.balance += amount
    db.session.commit()

    file_path = "config.txt"
    visit_doc(file_path, mode='add', para="coin_tot", value=amount)

    os.rename('templates/reads/' + filename + "/(undefined)preview.txt", 'templates/reads/' + filename + "/preview.txt")

    flash(f"审核通过文章：{filename}！给予 用户：{username} {amount} 个荣誉货币", 'success')
    return redirect(url_for('audit'))

@app.route('/audit_delete/<filename>', methods=['GET', 'POST'])
@login_required
def audit_delete(filename):
    os.rename('templates/reads/' + filename + "/(undefined)preview.txt", 'templates/reads/' + filename + "/(deleted)preview.txt")

    flash(f"审核拒绝文章：{filename}！", 'error')
    return redirect(url_for('audit'))

@app.route('/audit', methods=['GET', 'POST'])
@login_required
def audit():
    if request.method == "GET":
        query = request.args.get('query', '').lower()
        files = []
        for folder in os.listdir('templates/reads/'):
            if os.path.exists("templates/reads/" + folder + "/(undefined)preview.txt"):

                file_path = "templates/reads/" + folder + "/(undefined)preview.txt"
                params = visit_doc(file_path, mode='params')

                if ((query in folder.lower()) or (query in params['description'].lower())):
                    files.append({
                        "title": folder,
                        "user": params['user'],
                        "description": params['description'],
                        "link": '/audit_file/' + folder,
                        "state": "audit"
                    })

        return render_template("index.html", title='审核界面', files=files, state="audit")

@app.route('/', methods=['GET', 'POST'])
def index():
    file_path = 'config.txt'
    visit_doc(file_path, mode='add', para="views", value=1)

    if request.method == "GET":
        query = request.args.get('query', '').lower()
        print("Query:", query)
        files = []
        for folder in os.listdir('templates/reads/'):
            if os.path.exists("templates/reads/" + folder + "/preview.txt"):

                file_path = "templates/reads/" + folder + "/preview.txt"
                params = visit_doc(file_path, mode='params')

                if ((query in folder.lower()) or (query in params['description'].lower())):
                    files.append({
                        "title": folder,
                        "user": params['user'],
                        "description": params['description'],
                        "view" : params['view'],
                        "link": '/file/' + folder,
                        "state": "reads"
                    })
        #print(len(messages))
        return render_template("index.html", title='科学资源', qquery=query, files=files, state="reads")

colored_tag_lst = ['technology', 'biology', 'chemistry', 'math', 'physics', 'coding']

@app.route('/articles', methods=['GET', 'POST'])
@login_required
def view_all_articles():
    if request.method == "GET":
        file_path = 'config.txt'
        visit_doc(file_path, mode='add', para="views", value=1)

        articles = Article.query.filter(Article.status == 'published').all()
        return render_template('all_articles.html', articles=articles, mode='read', colored_tag_lst=colored_tag_lst)

@app.route('/audit_articles', methods=['GET', 'POST'])
@login_required
def audit_articles():
    if not current_user.is_admin:
        flash('You have no permission to this page!', 'danger')
        return redirect(url_for('index'))
    if request.method == "GET":
        file_path = 'config.txt'
        visit_doc(file_path, mode='add', para="views", value=1)

        articles = Article.query.filter(Article.status == 'draft').all()
        return render_template('all_articles.html', articles=articles, mode='audit', colored_tag_lst=colored_tag_lst)

@app.route('/create_tag', methods=['POST'])
@login_required
def create_tag():
    tag_name = request.form['tag_name']
    tag = Tag.query.filter_by(name=tag_name).first()

    if tag:
        return jsonify({'success': False, 'message': f'Tag "{tag_name}" already exists!'})

    new_tag = Tag(name=tag_name)
    db.session.add(new_tag)
    db.session.commit()

    return jsonify({'success': True, 'message': f'Tag "{tag_name}" created successfully!'})

# 创建文章路由
@app.route('/create_article', methods=['GET', 'POST'])
@login_required
def create_article():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        content = request.form['content']
        # 获取选中的标签（从隐藏的 input 获取标签的 ID）
        selected_tags = request.form.get('tags')  # 会返回一个逗号分隔的字符串
        selected_tags = selected_tags.split(',') if selected_tags else []
        #selected_tags = request.form.getlist('tags')

        # 1. 保存 Quill 内容为 HTML 文件
        filename = secure_filename(title) + ".html"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        # 保存 HTML 内容到文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # 2. 创建新的文章记录
        article = Article(
            title=title,
            description=description,
            content_path=file_path,
            user_id=current_user.id
        )

        # 添加标签
        print(article.tags)
        for tag_id in selected_tags:
            tag = Tag.query.get(tag_id)
            #print(tag)
            #print(article.tags)
            article.tags.append(tag)
            print(article.tags)

        print(article.tags)

        db.session.add(article)
        db.session.commit()

        flash('Article Created Successfully!', 'success')
        return redirect(url_for('view_article', article_id=article.id))

    # 获取所有标签
    tags = Tag.query.all()
    return render_template('create_article.html', tags=tags, title='Create Article')

@app.route('/view_article/<int:article_id>', methods=['GET', 'POST'])
def view_article(article_id):
    article = Article.query.get_or_404(article_id)
    # 从文件中读取 HTML 内容
    article.views += 1
    db.session.commit()
    with open(article.content_path, 'r', encoding='utf-8') as f:
        content_html = f.read()
    return render_template('view_article.html', article=article, content_html=content_html, title='View Article')

@app.route('/remove_tag_from_article/<int:article_id>/<int:tag_id>', methods=['DELETE'])
def remove_tag_from_article(article_id, tag_id):
    article = Article.query.get_or_404(article_id)
    tag = Tag.query.get_or_404(tag_id)

    # 检查标签是否在文章的标签列表中
    if tag in article.tags:
        article.tags.remove(tag)
        db.session.commit()  # 提交更改
        return jsonify({'success': True})

    return jsonify({'success': False, 'message': 'Tag not associated with article'})

@app.route('/manage_tags', methods=['GET', 'POST'])
@login_required
def manage_tags():
    if current_user.is_admin:
        tags = Tag.query.all()  # 获取所有标签和它们的文章数量
        return render_template('manage_tags.html', tags=tags, title='Manage Tags')

@app.route('/view_articles_by_tag/<int:tag_id>', methods=['GET'])
def view_articles_by_tag(tag_id):
    tag = Tag.query.get_or_404(tag_id)
    articles = tag.articles  # 获取该标签下的所有文章
    return render_template('view_articles_by_tag.html', tag=tag, articles=articles, title=f'View Articles by Tag {tag.name}')

@app.route('/delete_tag/<int:tag_id>', methods=['DELETE'])
def delete_tag(tag_id):
    tag = Tag.query.get(tag_id)
    if tag:
        db.session.delete(tag)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route("/html_test", methods=['GET', 'POST'])
def html_test():
    return render_template("html_test.html")

@app.route('/save', methods=['POST'])
def save():
    data = request.json
    html_content = data.get('html_content')

    with open('saved_content.html', 'w', encoding='utf-8') as f:
        f.write(html_content)

    return jsonify({"message": "Content saved successfully!"})

hostname = socket.gethostname()
ip_address = socket.gethostbyname(hostname)
if __name__ == '__main__':
    app.run(host=ip_address,port=8889, debug=True)
