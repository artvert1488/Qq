from flask import Flask, render_template, request, redirect, url_for, make_response, flash, jsonify, session
import uuid
from urllib.parse import quote
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename
from random import randint
import json
import secrets

app = Flask(__name__)
app.secret_key = 'your-secret-key'  # Замените на реальный секретный ключ

USERS_FILE = "users.json"

# Словарь для хранения активных приглашений
active_invites = {}

def load_users():
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return []
    except Exception as e:
        print(f"Error loading users: {e}")
        return []

def save_users(users_list):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users_list, f, indent=4, ensure_ascii=False)
        print(f"Users saved successfully to {USERS_FILE}")
    except Exception as e:
        print(f"Error saving users: {e}")

# Загружаем пользователей при запуске
users = load_users()

def login_required(f):
    def decorated_function(*args, **kwargs):
        if not request.cookies.get('logged_in'):
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login_page():
    error = None
    if request.method == "POST":
        name = request.form.get("name")
        password = request.form.get("password")
        print(f"Login attempt: name={name}, password={password}")
        
        # Перезагружаем пользователей из файла
        global users
        users = load_users()
        print(f"Loaded users: {users}")
        
        user = next((u for u in users if u["name"] == name and u["password"] == password), None)
        if user:
            print(f"User found: {user}")
            resp = make_response(redirect(url_for("profile_page")))
            resp.set_cookie("logged_in", "1", max_age=3600)
            resp.set_cookie("current_username", user["name"], max_age=3600)
            return resp
        else:
            error = "Неверные имя или пароль"
            print(f"Login failed: {error}")
    return render_template("login.html", error=error)

@app.route("/register", methods=["GET", "POST"])
def register_page():
    error = None
    if request.method == "POST":
        name = request.form.get("name")
        role = request.form.get("role")
        org = request.form.get("org")
        password = request.form.get("password")
        confirm = request.form.get("confirm")
        phone = request.form.get("phone")
        print(f"Register attempt: name={name}, role={role}, org={org}, phone={phone}")
        
        if not (name and role and org and password and confirm and phone):
            missing_fields = []
            if not name: missing_fields.append("имя")
            if not role: missing_fields.append("должность")
            if not org: missing_fields.append("организация")
            if not password: missing_fields.append("пароль")
            if not confirm: missing_fields.append("подтверждение пароля")
            if not phone: missing_fields.append("телефон")
            error = f"Заполните все поля. Отсутствуют: {', '.join(missing_fields)}"
            print(f"Registration error: {error}")
        elif password != confirm:
            error = "Пароли не совпадают"
            print(f"Registration error: {error}")
        else:
            # Перезагружаем пользователей из файла
            global users
            users = load_users()
            print(f"Current users in system: {users}")
            
            # Check if user already exists
            if any(u["name"] == name for u in users):
                error = "Пользователь с таким именем уже существует"
                print(f"Registration error: {error}")
            else:
                new_user = {
                    "name": name,
                    "role": role,
                    "org": org,
                    "password": password,
                    "phone": phone,
                    "avatar": None
                }
                users.append(new_user)
                print(f"Adding new user: {new_user}")
                try:
                    save_users(users)
                    print("Users saved successfully to file")
                    resp = make_response(redirect(url_for("profile_page")))
                    resp.set_cookie("logged_in", "1", max_age=3600)
                    resp.set_cookie("current_username", name, max_age=3600)
                    return resp
                except Exception as e:
                    error = "Ошибка при сохранении данных"
                    print(f"Error saving user data: {e}")
    return render_template("register.html", error=error)

@app.route("/profile")
@login_required
def profile_page():
    username = request.cookies.get("current_username")
    if not username:
        return redirect(url_for("login_page"))
    user = next((u for u in users if u["name"] == username), None)
    if not user:
        return redirect(url_for("login_page"))
    return render_template("profile.html", user=user)

@app.route("/edit_profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    username = request.cookies.get("current_username")
    if not username:
        return redirect(url_for("login_page"))
    
    user = next((u for u in users if u["name"] == username), None)
    if not user:
        return redirect(url_for("login_page"))
    
    if request.method == "POST":
        name = request.form.get("name")
        phone = request.form.get("phone")
        password = request.form.get("password")
        confirm = request.form.get("confirm")
        
        # Handle avatar upload
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename:
                # Generate unique filename
                filename = secure_filename(f"{username}_{int(datetime.now().timestamp())}_{file.filename}")
                file_path = os.path.join('static/avatars', filename)
                
                # Save the file
                file.save(file_path)
                
                # Delete old avatar if exists
                if user.get('avatar'):
                    old_avatar_path = os.path.join('static/avatars', user['avatar'])
                    if os.path.exists(old_avatar_path):
                        os.remove(old_avatar_path)
                
                user['avatar'] = filename
        
        # Update user info
        user['name'] = name
        user['phone'] = phone
        
        # Update password if provided
        if password and confirm and password == confirm:
            user['password'] = password
        
        # Save changes
        save_users(users)
        
        # Update cookies
        resp = make_response(redirect(url_for("profile_page")))
        resp.set_cookie("current_username", name, max_age=3600)
        return resp
    
    return render_template("edit_profile.html", user=user)

@app.route("/tasks")
@login_required
def tasks_page():
    username = request.cookies.get("current_username")
    user = next((u for u in users if u["name"] == username), None)
    return render_template("tasks.html", user=user)

@app.route("/shifts")
@login_required
def shifts_page():
    username = request.cookies.get("current_username")
    user = next((u for u in users if u["name"] == username), None)
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template("shifts.html", user=user, today_date=today)

@app.route("/purchases")
@login_required
def purchases_page():
    username = request.cookies.get("current_username")
    user = next((u for u in users if u["name"] == username), None)
    return render_template("purchases.html", user=user)

@app.route("/chat")
@login_required
def chat_page():
    username = request.cookies.get("current_username")
    user = next((u for u in users if u["name"] == username), None)
    return render_template("chat.html", user=user)

@app.route("/notes")
@login_required
def notes_page():
    username = request.cookies.get("current_username")
    user = next((u for u in users if u["name"] == username), None)
    return render_template("notes.html", user=user)

@app.route("/calculator")
@login_required
def calculator_page():
    username = request.cookies.get("current_username")
    user = next((u for u in users if u["name"] == username), None)
    return render_template("calculator.html", user=user)

@app.route("/analytics")
@login_required
def analytics_page():
    username = request.cookies.get("current_username")
    user = next((u for u in users if u["name"] == username), None)
    return render_template("analytics.html", user=user)

@app.route("/logout")
def logout():
    resp = make_response(redirect(url_for("login_page")))
    resp.delete_cookie("logged_in")
    resp.delete_cookie("current_username")
    return resp

def generate_invite_link():
    """Генерирует уникальную ссылку для приглашения"""
    code = secrets.token_urlsafe(16)
    active_invites[code] = {
        'created': datetime.now(),
        'expires': datetime.now() + timedelta(days=1),
        'role': 'chef'  # По умолчанию
    }
    return f"http://your-domain.com/invite/{code}"  # Замените your-domain.com на ваш реальный домен

@app.route('/invite')
@login_required
def invite():
    """Страница приглашения сотрудников"""
    username = request.cookies.get("current_username")
    if not username:
        return redirect(url_for("login_page"))
    invite_link = generate_invite_link()
    return render_template('invite.html', invite_link=invite_link)

@app.route('/invite/<code>')
def process_invite(code):
    """Обработка приглашения по коду"""
    if code in active_invites:
        invite_data = active_invites[code]
        if datetime.now() < invite_data['expires']:
            return render_template('register.html', invite_code=code, role=invite_data['role'])
    return redirect(url_for('login_page'))

@app.route('/api/generate_invite', methods=['POST'])
@login_required
def generate_invite():
    """API для генерации новой ссылки приглашения"""
    username = request.cookies.get("current_username")
    if not username:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    role = data.get('role', 'chef')
    code = secrets.token_urlsafe(16)
    active_invites[code] = {
        'created': datetime.now(),
        'expires': datetime.now() + timedelta(days=1),
        'role': role
    }
    return jsonify({
        'link': f"http://127.0.0.1:5000/invite/{code}",
        'expires': active_invites[code]['expires'].isoformat()
    })

@app.route('/api/revoke_invite/<code>', methods=['POST'])
@login_required
def revoke_invite(code):
    """API для отзыва приглашения"""
    username = request.cookies.get("current_username")
    if not username:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if code in active_invites:
        del active_invites[code]
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'Invite not found'}), 404

@app.route('/api/active_invites')
@login_required
def get_active_invites():
    """API для получения списка активных приглашений"""
    username = request.cookies.get("current_username")
    if not username:
        return jsonify({'error': 'Unauthorized'}), 401
    
    invites = []
    for code, data in active_invites.items():
        if datetime.now() < data['expires']:
            invites.append({
                'code': code,
                'role': data['role'],
                'created': data['created'].isoformat(),
                'expires': data['expires'].isoformat()
            })
    return jsonify(invites)

@app.route("/team", methods=["GET", "POST"])
@login_required
def team_page():
    global users
    username = request.cookies.get("current_username")
    user = next((u for u in users if u["name"] == username), None)
    if not user or user.get("role") != "Шеф-повар":
        return redirect(url_for("profile_page"))

    if request.method == "POST":
        remove_name = request.form.get("remove_name")
        if remove_name and remove_name != username:
            users = [u for u in users if u["name"] != remove_name]
            save_users(users)
            flash(f"Сотрудник {remove_name} удалён.", "success")
        elif remove_name == username:
            flash("Нельзя удалить самого себя.", "danger")

    return render_template("team.html", users=users, user=user)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True) 