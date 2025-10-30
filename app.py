from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime

# ----------------------------------------
# ✅ Initialize Flask app
# ----------------------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'

# ✅ MySQL connection
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/flaskbook_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ----------------------------------------
# ✅ Database Models
# ----------------------------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    posts = db.relationship('Post', backref='author', lazy=True)
    tasks = db.relationship('Task', backref='user', lazy=True)
    help_requests = db.relationship('HelpRequest', backref='user', lazy=True)
    replies = db.relationship('HelpReply', backref='user', lazy=True)


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(200))
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


# ✅ Task model (Assignments, Projects, Exams)
class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(100))
    due_date = db.Column(db.Date)
    is_completed = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


# ✅ NEW: Help Request and Reply models
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


# ----------------------------------------
# ✅ Flask-Login Loader
# ----------------------------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ----------------------------------------
# ✅ Routes
# ----------------------------------------
@app.route('/')
def index():
    search_query = request.args.get('search', '', type=str)
    filter_user = request.args.get('user', '', type=str)
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

    if sort_order == 'oldest':
        query = query.order_by(Post.date_posted.asc())
    else:
        query = query.order_by(Post.date_posted.desc())

    posts = query.paginate(page=page, per_page=per_page)
    all_users = User.query.all()

    return render_template(
        'index.html',
        posts=posts,
        search_query=search_query,
        filter_user=filter_user,
        sort_order=sort_order,
        all_users=all_users,
        user=current_user
    )

# ----------------------------------------
# ✅ Auth Routes
# ----------------------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()

        if not username or not password:
            flash('Username and password are required!', 'danger')
            return redirect(url_for('register'))

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose another.', 'warning')
            return redirect(url_for('register'))

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'warning')
            return redirect(url_for('register'))

        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()

        flash('✅ Account created successfully! You can now log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()

        if not username or not password:
            flash('Please enter both username and password.', 'danger')
            return redirect(url_for('login'))

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash(f'👋 Welcome back, {user.username}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ----------------------------------------
# ✅ Post Routes
# ----------------------------------------
@app.route('/create', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        content = request.form['content'].strip()
        image = request.files.get('image')

        if not content and not image:
            flash('Post cannot be empty. Add text or an image.', 'warning')
            return redirect(url_for('create_post'))

        image_path = None
        if image and image.filename != '':
            image_filename = image.filename
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
            image.save(image_path)

        new_post = Post(content=content, image=image_path, author=current_user)
        db.session.add(new_post)
        db.session.commit()
        flash('📝 Post created successfully!', 'success')
        return redirect(url_for('index'))

    return render_template('create_post.html')


@app.route('/edit/<int:post_id>', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        flash('You can only edit your own posts.')
        return redirect(url_for('index'))

    if request.method == 'POST':
        post.content = request.form['content']
        db.session.commit()
        return redirect(url_for('index'))

    return render_template('edit_post.html', post=post)


@app.route('/delete/<int:post_id>')
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        flash('You can only delete your own posts.')
        return redirect(url_for('index'))

    db.session.delete(post)
    db.session.commit()
    return redirect(url_for('index'))

# ----------------------------------------
# ✅ Task Routes
# ----------------------------------------
@app.route('/tasks')
@login_required
def tasks():
    tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.due_date.asc()).all()
    return render_template('tasks.html', tasks=tasks)


@app.route('/tasks/create', methods=['GET', 'POST'])
@login_required
def create_task():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        category = request.form['category']
        due_date = request.form['due_date']

        new_task = Task(
            title=title,
            description=description,
            category=category,
            due_date=due_date,
            user_id=current_user.id
        )
        db.session.add(new_task)
        db.session.commit()
        flash('✅ Task created successfully!', 'success')
        return redirect(url_for('tasks'))

    return render_template('create_task.html')


@app.route('/tasks/complete/<int:task_id>')
@login_required
def complete_task(task_id):
    task = Task.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        flash('⛔ You cannot complete another user’s task.', 'danger')
        return redirect(url_for('tasks'))

    task.is_completed = True
    db.session.commit()
    flash('✅ Task marked as completed!', 'success')
    return redirect(url_for('tasks'))


@app.route('/tasks/delete/<int:task_id>')
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        flash('⛔ You cannot delete another user’s task.', 'danger')
        return redirect(url_for('tasks'))

    db.session.delete(task)
    db.session.commit()
    flash('🗑️ Task deleted successfully!', 'info')
    return redirect(url_for('tasks'))

# ----------------------------------------
# ✅ Help Request Routes (New Feature)
# ----------------------------------------
@app.route('/help')
@login_required
def help_requests():
    requests = HelpRequest.query.order_by(HelpRequest.date_posted.desc()).all()
    return render_template('help_requests.html', requests=requests)


@app.route('/help/create', methods=['GET', 'POST'])
@login_required
def create_help_request():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        subject = request.form['subject']

        new_request = HelpRequest(
            title=title,
            description=description,
            subject=subject,
            user_id=current_user.id
        )
        db.session.add(new_request)
        db.session.commit()
        flash('🆘 Help request posted successfully!', 'success')
        return redirect(url_for('help_requests'))

    return render_template('create_help_request.html')


@app.route('/help/<int:request_id>', methods=['GET', 'POST'])
@login_required
def help_detail(request_id):
    help_request = HelpRequest.query.get_or_404(request_id)
    replies = HelpReply.query.filter_by(request_id=request_id).order_by(HelpReply.date_posted.asc()).all()

    if request.method == 'POST':
        content = request.form['content']
        if not content:
            flash('Reply cannot be empty.', 'warning')
        else:
            new_reply = HelpReply(content=content, user_id=current_user.id, request_id=request_id)
            db.session.add(new_reply)
            db.session.commit()
            flash('💬 Reply added successfully!', 'success')
        return redirect(url_for('help_detail', request_id=request_id))

    return render_template('help_detail.html', help_request=help_request, replies=replies)

# ----------------------------------------
# ✅ Test + Run
# ----------------------------------------
@app.route('/test')
def test():
    return "<h1>Flask is working!</h1>"


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
