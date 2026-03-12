from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os

app = Flask(__name__, static_folder='static', static_url_path='/static', template_folder='templates')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_secret_key_here') # In a real app, use a secure random string
app.config['UPLOAD_FOLDER'] = 'static/images/gallery'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16MB max file size

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Database setup
DATABASE = 'database.sqlite'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    # Create users table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    # Create gallery table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS gallery (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL
        )
    ''')

    # Create default admin user if none exists
    user = conn.execute('SELECT * FROM users WHERE username = ?', ('admin',)).fetchone()
    if not user:
        hashed_password = generate_password_hash(os.environ.get("ADMIN_PASSWORD", "password123"), method="pbkdf2:sha256")
        conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', ('admin', hashed_password))

    # Seed initial images if gallery is empty
    count = conn.execute('SELECT COUNT(*) FROM gallery').fetchone()[0]
    if count == 0:
        initial_images = [
            ('exhibit-1.jpg', 'Pioneer Tools', 'exhibits'),
            ('exhibit-2.jpg', 'Early Settlers Clothing', 'exhibits'),
            ('event-1.jpg', 'Annual Heritage Festival', 'events'),
            ('event-2.jpg', 'School Field Trip', 'events'),
            ('archive-1.jpg', '19th Century Maps', 'archives'),
            ('archive-2.jpg', 'Historical Documents', 'archives')
        ]
        conn.executemany('INSERT INTO gallery (filename, title, category) VALUES (?, ?, ?)', initial_images)

    conn.commit()
    conn.close()

# Initialize DB on startup
with app.app_context():
    init_db()

# Login Manager setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if user:
        return User(user['id'], user['username'])
    return None

# --- Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about.html')
def about():
    return render_template('about.html')

@app.route('/museum.html')
def museum():
    return render_template('museum.html')

@app.route('/gallery.html')
def gallery():
    conn = get_db_connection()
    images = conn.execute('SELECT * FROM gallery ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('gallery.html', images=images)

@app.route('/contact.html')
def contact():
    return render_template('contact.html')

# Authentication routes

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            user_obj = User(user['id'], user['username'])
            login_user(user_obj)
            return redirect(url_for('admin'))
        else:
            flash('Invalid username or password')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Admin routes

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    if request.method == 'POST':
        # Check if the post request has the file part
        if 'image' not in request.files:
            flash('No file part')
            return redirect(request.url)

        file = request.files['image']
        title = request.form.get('title')
        category = request.form.get('category')

        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Ensure unique filename
            base, extension = os.path.splitext(filename)
            counter = 1
            while os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], filename)):
                filename = f"{base}_{counter}{extension}"
                counter += 1

            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            conn = get_db_connection()
            conn.execute('INSERT INTO gallery (filename, title, category) VALUES (?, ?, ?)',
                         (filename, title, category))
            conn.commit()
            conn.close()

            flash('Image successfully uploaded')
            return redirect(url_for('admin'))

    # GET request: fetch existing images
    conn = get_db_connection()
    images = conn.execute('SELECT * FROM gallery ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('admin.html', images=images)

@app.route('/admin/delete/<int:image_id>', methods=['POST'])
@login_required
def delete_image(image_id):
    conn = get_db_connection()
    image = conn.execute('SELECT filename FROM gallery WHERE id = ?', (image_id,)).fetchone()

    if image:
        # Delete file from filesystem
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], image['filename'])
        if os.path.exists(file_path):
            os.remove(file_path)

        # Delete from DB
        conn.execute('DELETE FROM gallery WHERE id = ?', (image_id,))
        conn.commit()
        flash('Image deleted successfully')

    conn.close()
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
