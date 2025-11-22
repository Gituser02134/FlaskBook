from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user,
    login_required, logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime

# ----------------------------------------
# Initialize Flask
# ----------------------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/flaskbook_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Setup
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ✅ Enable SocketIO
from flask_socketio import SocketIO, emit, join_room, leave_room
socketio = SocketIO(app, cors_allowed_origins="*")


# ----------------------------------------
# Allowed file types
# ----------------------------------------
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'docx', 'ppt', 'pptx'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ----------------------------------------
# Models
# ----------------------------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

    posts = db.relationship('Post', backref='author', lazy=True)
    tasks = db.relationship('Task', backref='user', lazy=True)
    help_requests = db.relationship('HelpRequest', backref='user', lazy=True)
    replies = db.relationship('HelpReply', backref='user', lazy=True)
    blogs = db.relationship('Blog', backref='author', lazy=True)  # ✅ Blog relationship


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    file = db.Column(db.String(200))
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(100))
    due_date = db.Column(db.Date)
    is_completed = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


class HelpRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    subject = db.Column(db.String(100))
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    replies = db.relationship('HelpReply', backref='request', cascade="all, delete", lazy=True)


class HelpReply(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    request_id = db.Column(db.Integer, db.ForeignKey('help_request.id'), nullable=False)


# ✅ Blog model must be declared OUTSIDE other models (same indentation level)
class Blog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ----------------------------------------
# Index / Feed
# ----------------------------------------
@app.route('/')
def index():
    search_query = request.args.get('search', '', type=str)
    filter_user = request.args.get('user', '', type=str)
    filter_subject = request.args.get('subject', '', type=str)
    sort_order = request.args.get('sort', 'newest', type=str)
    page = request.args.get('page', 1, type=int)
    per_page = 5

    query = Post.query.join(User)

    if search_query:
        query = query.filter(
            (Post.content.like(f"%{search_query}%")) |
            (User.username.like(f"%{search_query}%"))
        )

    if filter_user:
        query = query.filter(User.username == filter_user)

    if filter_subject:
        query = query.filter(Post.content.like(f"%{filter_subject}%"))

    query = query.order_by(Post.date_posted.desc() if sort_order == 'newest' else Post.date_posted.asc())
    posts = query.paginate(page=page, per_page=per_page)
    all_users = User.query.all()

    return render_template('index.html',
                           posts=posts,
                           search_query=search_query,
                           filter_user=filter_user,
                           filter_subject=filter_subject,
                           sort_order=sort_order,
                           all_users=all_users)


# ----------------------------------------
# Register / Login / Logout
# ----------------------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()

        if not username or not password:
            flash('Username and password are required!', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'warning')
            return redirect(url_for('register'))

        hashed_pw = generate_password_hash(password)
        db.session.add(User(username=username, password=hashed_pw))
        db.session.commit()
        flash('Account created! You can now log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            flash(f'Welcome back, {user.username}!', 'success')
            return redirect(url_for('index'))

        flash('Invalid username or password.', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ----------------------------------------
# Chat Route
# ----------------------------------------
@app.route('/chat')
@login_required
def chat():
    return render_template('chat.html', username=current_user.username)

# SocketIO events
@socketio.on('send_message')
def handle_send_message(data):
    message = data['message']
    username = data['username']
    emit('receive_message', {'username': username, 'message': message}, broadcast=True)

    @app.route('/chat')
    @login_required
    def chat():
        return render_template('chat.html', username=current_user.username)


# ----------------------------------------
# ✅ SocketIO Events for Real-Time Chat
# ----------------------------------------
@socketio.on('connect')
def handle_connect():
    print(f"🔌 {current_user.username if current_user.is_authenticated else 'Guest'} connected")

@socketio.on('disconnect')
def handle_disconnect():
    print(f"❌ {current_user.username if current_user.is_authenticated else 'Guest'} disconnected")

@socketio.on('send_message')
def handle_send_message(data):
    username = data.get('username', 'Anonymous')
    message = data.get('message', '')
    if message.strip():
        emit('receive_message', {'username': username, 'message': message}, broadcast=True)


# ----------------------------------------
# Create Post
# ----------------------------------------
@app.route('/create_post', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        content = request.form['content']
        uploaded = request.files.get('file')
        filename = None

        if uploaded and allowed_file(uploaded.filename):
            filename = secure_filename(uploaded.filename)
            uploaded.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            filename = f"uploads/{filename}"

        new_post = Post(content=content, file=filename, author=current_user)
        db.session.add(new_post)
        db.session.commit()

        flash('Post created!', 'success')
        return redirect(url_for('index'))

    return render_template('create_post.html')


# ----------------------------------------
# Edit / Delete Post
# ----------------------------------------
@app.route('/edit_post/<int:post_id>', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)

    if post.author != current_user:
        flash('You cannot edit this post.', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        post.content = request.form['content']
        db.session.commit()
        flash('Post updated!', 'success')
        return redirect(url_for('index'))

    return render_template('edit_post.html', post=post)


@app.route('/delete_post/<int:post_id>')
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)

    if post.author != current_user:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('index'))

    db.session.delete(post)
    db.session.commit()
    flash('Post deleted!', 'info')
    return redirect(url_for('index'))


# ----------------------------------------
# Tasks
# ----------------------------------------
@app.route('/tasks')
@login_required
def tasks():
    category = request.args.get('category', '', type=str)
    status = request.args.get('status', 'all', type=str)

    query = Task.query.filter_by(user_id=current_user.id)

    if category:
        query = query.filter(Task.category.like(f"%{category}%"))

    if status == 'completed':
        query = query.filter_by(is_completed=True)
    elif status == 'pending':
        query = query.filter_by(is_completed=False)

    tasks = query.order_by(Task.due_date.asc()).all()
    categories = [c[0] for c in db.session.query(Task.category).distinct().all()]

    return render_template('tasks.html',
                           tasks=tasks,
                           categories=categories,
                           selected_category=category)


@app.route('/create_task', methods=['GET', 'POST'])
@login_required
def create_task():
    if request.method == 'POST':
        title = request.form['title']
        category = request.form.get('category', '')
        due_date_val = request.form.get('due_date')

        due_date = datetime.strptime(due_date_val, '%Y-%m-%d') if due_date_val else None

        new_task = Task(title=title, category=category, due_date=due_date,
                        user_id=current_user.id)
        db.session.add(new_task)
        db.session.commit()

        flash('Task added!', 'success')
        return redirect(url_for('tasks'))

    return render_template('create_task.html')


@app.route('/complete_task/<int:task_id>')
@login_required
def complete_task(task_id):
    task = Task.query.get_or_404(task_id)

    if task.user_id != current_user.id:
        flash('Unauthorized!', 'danger')
        return redirect(url_for('tasks'))

    task.is_completed = True
    db.session.commit()

    flash('Task marked completed!', 'success')
    return redirect(url_for('tasks'))


@app.route('/delete_task/<int:task_id>')
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)

    if task.user_id != current_user.id:
        flash('Unauthorized!', 'danger')
        return redirect(url_for('tasks'))

    db.session.delete(task)
    db.session.commit()

    flash('Task deleted!', 'info')
    return redirect(url_for('tasks'))


# ----------------------------------------
# Help Requests
# ----------------------------------------
@app.route('/help')
@login_required
def help_requests():
    subject = request.args.get('subject', '', type=str)
    search = request.args.get('search', '', type=str)

    query = HelpRequest.query

    if subject:
        query = query.filter(HelpRequest.subject.like(f"%{subject}%"))

    if search:
        query = query.filter(
            (HelpRequest.title.like(f"%{search}%")) |
            (HelpRequest.description.like(f"%{search}%"))
        )

    help_requests = query.order_by(HelpRequest.date_posted.desc()).all()
    subjects = [s[0] for s in db.session.query(HelpRequest.subject).distinct().all()]

    return render_template('help_requests.html',
                           help_requests=help_requests,
                           subjects=subjects)


@app.route('/create_help_request', methods=['GET', 'POST'])
@login_required
def create_help_request():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        subject = request.form.get('subject', '')

        req = HelpRequest(title=title, description=description,
                          subject=subject, user_id=current_user.id)
        db.session.add(req)
        db.session.commit()

        flash('Help request posted!', 'success')
        return redirect(url_for('help_requests'))

    return render_template('create_help_request.html')


# ----------------------------------------
# Help Request Detail + Reply Posting
# ----------------------------------------
@app.route('/help/<int:help_id>')
@login_required
def help_detail(help_id):
    help_request = HelpRequest.query.get_or_404(help_id)
    return render_template('help_detail.html', help_request=help_request)


@app.route('/help/<int:help_id>/reply', methods=['POST'])
@login_required
def add_reply(help_id):
    help_request = HelpRequest.query.get_or_404(help_id)
    content = request.form.get('reply')

    if not content:
        flash("Reply cannot be empty.", "warning")
        return redirect(url_for('help_detail', help_id=help_id))

    new_reply = HelpReply(content=content,
                          user_id=current_user.id,
                          request_id=help_id)

    db.session.add(new_reply)
    db.session.commit()

    flash("Reply posted!", "success")
    return redirect(url_for('help_detail', help_id=help_id))

# ----------------------------------------
# Blogs
# ----------------------------------------
@app.route('/blogs')
@login_required
def blogs():
    all_blogs = Blog.query.order_by(Blog.date_posted.desc()).all()
    return render_template('blogs.html', blogs=all_blogs)


@app.route('/blog/<int:blog_id>')
@login_required
def blog_detail(blog_id):
    blog = Blog.query.get_or_404(blog_id)
    return render_template('blog_detail.html', blog=blog)


@app.route('/create_blog', methods=['GET', 'POST'])
@login_required
def create_blog():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']

        if not title or not content:
            flash('Title and content are required.', 'warning')
            return redirect(url_for('create_blog'))

        new_blog = Blog(title=title, content=content, author=current_user)
        db.session.add(new_blog)
        db.session.commit()
        flash('📝 Blog published successfully!', 'success')
        return redirect(url_for('blogs'))

    return render_template('create_blog.html')




# ----------------------------------------
# Dashboard
# ----------------------------------------
@app.route('/dashboard')
@login_required
def dashboard():
    recent_posts = Post.query.filter_by(user_id=current_user.id).order_by(Post.date_posted.desc()).limit(5).all()
    upcoming_tasks = Task.query.filter_by(user_id=current_user.id, is_completed=False).order_by(
        Task.due_date.asc()).limit(5).all()

    total_tasks = Task.query.filter_by(user_id=current_user.id).count()
    completed_tasks = Task.query.filter_by(user_id=current_user.id, is_completed=True).count()
    pending_tasks = total_tasks - completed_tasks

    return render_template('dashboard.html',
                           recent_posts=recent_posts,
                           upcoming_tasks=upcoming_tasks,
                           total_tasks=total_tasks,
                           completed_tasks=completed_tasks,
                           pending_tasks=pending_tasks)


# ----------------------------------------
# Run
# ----------------------------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True)

