from flask import Flask, render_template, request, redirect, url_for, make_response, flash
import uuid
from urllib.parse import quote
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename
from random import randint
import json

app = Flask(__name__)

USERS_FILE = "users.json"

def load_users():
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return []
    except Exception as e:
        print(f"Error loading users: {e}")
        return []

def save_users():
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=4, ensure_ascii=False)
        print(f"Users saved successfully to {USERS_FILE}")
    except Exception as e:
        print(f"Error saving users: {e}")

class TeamMember:
    def __init__(self, name, role):
        self.name = name
        self.role = role
        self.tasks = []

    def assign_task(self, task):
        self.tasks.append(task)

team = [
    TeamMember("Иван", "Шеф-повар"),
    TeamMember("Анна", "Су-шеф"),
    TeamMember("Петр", "Повар")
]

def find_member(name):
    for member in team:
        if member.name == name:
            return member
    return None

def _(text):
    return text

def get_current_user():
    username = request.cookies.get("current_username")
    if username:
        return next((u for u in users if u["name"] == username), None)
    return None

@app.context_processor
def inject_translations():
    return dict(_=_, current_user=get_current_user())

@app.route("/")
def index():
    return render_template("index.html", team=team)

@app.route("/add_member", methods=["POST"])
def add_member():
    name = request.form["name"]
    role = request.form["role"]
    if name and role:
        team.append(TeamMember(name, role))
    return redirect(url_for("index"))

@app.route("/assign_task", methods=["POST"])
def assign_task():
    member_name = request.form["member_name"]
    task = request.form["task"]
    member = find_member(member_name)
    if member and task:
        member.assign_task(task)
    return redirect(url_for("index"))

@app.route("/team")
def team_page():
    return render_template("team.html")

# --- Хранилища для сущностей ---
tasks = []
shifts = []
purchases = []
chat_messages = []
notes = []
users = load_users() # Load users on startup
invites = {}  # invite_id: {'org': ..., 'role': ..., 'name': ..., 'created_by': ...}
chat_private = {}  # (user1, user2): [ {author, text} ]
analytics_scores = {}  # {user: {date: score}}
purchases_history = []  # [{'date': 'YYYY-MM-DD', 'products': [...] }]
reset_codes = {}  # phone: code

AVATAR_FOLDER = os.path.join("static", "avatars")
os.makedirs(AVATAR_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/tasks", methods=["GET", "POST"])
def tasks_page():
    if request.method == "POST":
        description = request.form.get("description")
        assignees = request.form.getlist("assignees")
        deadline = request.form.get("deadline")
        if description and assignees:
            tasks.append({"description": description, "assignees": assignees, "deadline": deadline})
        return redirect(url_for("tasks_page"))
    return render_template("tasks.html", tasks=tasks, team=team)

@app.route("/shifts", methods=["GET", "POST"])
def shifts_page():
    def calc_hours(start, end):
        try:
            t1 = datetime.strptime(start, '%H:%M')
            t2 = datetime.strptime(end, '%H:%M')
            delta = (t2 - t1).seconds / 3600
            return round(delta, 2)
        except:
            return ''
    if request.method == "POST":
        user = request.form.get("user")
        date = request.form.get("date")
        time_in = request.form.get("time_in")
        time_out = request.form.get("time_out")
        if user and date and time_in and time_out:
            hours = calc_hours(time_in, time_out)
            shifts.append({"user": user, "date": date, "time_in": time_in, "time_out": time_out, "hours": hours})
        return redirect(url_for("shifts_page"))
    return render_template("shifts.html", shifts=shifts, team=team)

@app.route("/purchases", methods=["GET", "POST"])
def purchases_page():
    if request.method == "POST":
        if 'refresh' in request.form:
            # Сохраняем текущий список в историю
            if purchases:
                purchases_history.append({
                    'date': datetime.now().date().isoformat(),
                    'products': [p['products'] for p in purchases]
                })
                # Оставляем только последние 7 дней
                cutoff = datetime.now().date() - timedelta(days=7)
                purchases_history[:] = [h for h in purchases_history if datetime.fromisoformat(h['date']).date() >= cutoff]
                purchases.clear()
            return redirect(url_for("purchases_page"))
        else:
            products = request.form.get("products")
            if products:
                purchases.append({"products": products})
            return redirect(url_for("purchases_page"))
    return render_template("purchases.html", purchases=purchases, purchases_history=purchases_history)

@app.route("/chat", methods=["GET", "POST"])
def chat_page():
    chat_type = request.args.get('type', 'public')
    current_user = get_current_user()
    if not current_user: # Redirect if no user is logged in
        return redirect(url_for("login_page"))
    current_username = current_user["name"]
    private_with = request.args.get('with', None)
    private_messages = []
    if chat_type == 'private' and private_with:
        key = tuple(sorted([current_username, private_with]))
        if request.method == "POST":
            text = request.form.get("text")
            if text:
                chat_private.setdefault(key, []).append({"author": current_username, "text": text})
            return redirect(url_for("chat_page", type='private', **{'with': private_with}))
        private_messages = chat_private.get(key, [])
    elif chat_type == 'public':
        if request.method == "POST":
            author = current_username # Use current_username as author for public chat
            text = request.form.get("text")
            if author and text:
                chat_messages.append({"author": author, "text": text})
            return redirect(url_for("chat_page"))
    return render_template("chat.html", chat_type=chat_type, chat_messages=chat_messages, private_messages=private_messages, private_with=private_with, team=team, users=users, current_user=current_username)

@app.route("/notes", methods=["GET", "POST"])
def notes_page():
    if request.method == "POST":
        title = request.form.get("title")
        text = request.form.get("text")
        if title and text:
            notes.append({"title": title, "text": text})
        return redirect(url_for("notes_page"))
    return render_template("notes.html", notes=notes)

@app.route("/calculator", methods=["GET", "POST"])
def calculator_page():
    result = None
    if request.method == "POST":
        try:
            price_per_kg = float(request.form.get("price_per_kg", 0))
            grams = float(request.form.get("grams", 0))
            result = round(price_per_kg * grams / 1000, 2)
        except Exception:
            result = "Ошибка ввода"
    return render_template("calculator.html", result=result)

@app.before_request
def require_login():
    allowed = ["login_page", "register_page", "forgot_password", "enter_code", "reset_password", "static"]
    if request.endpoint not in allowed and not request.cookies.get("logged_in"):
        return redirect(url_for("login_page"))

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
            resp.set_cookie("logged_in", "1", max_age=3600)  # Кука на 1 час
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
            error = "Заполните все поля"
            print(f"Registration error: {error}")
        elif password != confirm:
            error = "Пароли не совпадают"
            print(f"Registration error: {error}")
        else:
            # Перезагружаем пользователей из файла
            global users
            users = load_users()
            
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
                print(f"User appended: {new_user}")
                save_users()
                print("Users saved to file.")
                resp = make_response(redirect(url_for("profile_page")))
                resp.set_cookie("logged_in", "1", max_age=3600)
                resp.set_cookie("current_username", name, max_age=3600)
                return resp
    return render_template("register.html", error=error)

@app.route("/profile", methods=["GET", "POST"])
def profile_page():
    user = get_current_user()
    if not user: # Redirect if no user is logged in
        return redirect(url_for("login_page"))
    return render_template("profile.html", user=user)

@app.route("/logout")
def logout_page():
    resp = make_response(redirect(url_for("login_page")))
    resp.delete_cookie("logged_in")
    resp.delete_cookie("current_username")
    return resp

@app.route("/set_lang/<lang>")
def set_lang(lang):
    # Здесь можно реализовать смену языка, пока просто редирект на главную
    return redirect(url_for("index"))

@app.route("/invite", methods=["GET", "POST"])
def invite_page():
    user = get_current_user()
    if not user or user.get("role") != "Шеф-повар":
        return redirect(url_for("profile_page"))
    invite_link = None
    qr_url = None
    if request.method == "POST":
        name = request.form.get("name")
        role = request.form.get("role")
        if name and role:
            invite_id = str(uuid.uuid4())
            invites[invite_id] = {
                "org": user["org"],
                "role": role,
                "name": name,
                "created_by": user["name"]
            }
            invite_link = request.host_url.rstrip("/") + url_for("invite_register", invite_id=invite_id)
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={quote(invite_link)}"
    return render_template("invite.html", invite_link=invite_link, qr_url=qr_url, users=users) # Pass users for dropdown

@app.route("/invite/<invite_id>", methods=["GET", "POST"])
def invite_register(invite_id):
    invite = invites.get(invite_id)
    error = None
    if not invite:
        return "Приглашение не найдено или устарело.", 404
    if request.method == "POST":
        password = request.form.get("password")
        confirm = request.form.get("confirm")
        if not (password and confirm):
            error = "Заполните все поля"
        elif password != confirm:
            error = "Пароли не совпадают"
        else:
            # Check if user already exists (important for invites too)
            if any(u["name"] == invite["name"] for u in users):
                error = "Пользователь с таким именем уже существует"
            else:
                users.append({
                    "name": invite["name"],
                    "role": invite["role"],
                    "org": invite["org"],
                    "password": password
                })
                save_users() # Save users after invite registration
                invites.pop(invite_id)
                resp = make_response(redirect(url_for("profile_page"))) # Redirect directly to profile page
                resp.set_cookie("logged_in", "1")
                resp.set_cookie("current_username", invite["name"]) # Set current_username for invite registered users
                return resp
    return render_template("invite_register.html", invite=invite, error=error)

@app.route("/analytics", methods=["GET", "POST"])
def analytics_page():
    today = datetime.now().date()
    week_dates = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]  # последние 7 дней
    if request.method == "POST":
        user = request.form.get("user")
        date = request.form.get("date")
        score = request.form.get("score")
        if user and date and score:
            analytics_scores.setdefault(user, {})[date] = int(score)
        return redirect(url_for("analytics_page"))
    # Готовим данные для таблицы
    table = []
    for user in users:
        row = {"name": user["name"], "scores": [], "avg": None}
        scores = analytics_scores.get(user["name"], {})
        vals = []
        for d in week_dates:
            val = scores.get(d)
            row["scores"].append(val)
            if val is not None:
                vals.append(val)
        row["avg"] = round(sum(vals)/len(vals), 2) if vals else None
        table.append(row)
    return render_template("analytics.html", week_dates=week_dates, table=table, users=users)

@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    error = None
    code_sent = False
    phone = None
    if request.method == "POST":
        phone = request.form.get("phone")
        user = next((u for u in users if u.get("phone") == phone), None)
        if user:
            code = str(randint(1000, 9999))
            reset_codes[phone] = code
            code_sent = True
            # В реальном проекте: отправить SMS через API
            return render_template("enter_code.html", phone=phone, code=code)  # code показываем для теста
        else:
            error = "Пользователь с таким номером не найден."
    return render_template("forgot_password.html", error=error)

@app.route("/enter_code", methods=["GET", "POST"])
def enter_code():
    phone = request.args.get("phone")
    error = None
    if request.method == "POST":
        code = request.form.get("code")
        if reset_codes.get(phone) == code:
            return redirect(url_for("reset_password", phone=phone))
        else:
            error = "Неверный код. Попробуйте ещё раз."
    return render_template("enter_code.html", phone=phone, code=None, error=error)

@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    phone = request.args.get("phone")
    user = next((u for u in users if u.get("phone") == phone), None)
    error = None
    if not user:
        return "Пользователь не найден", 404
    if request.method == "POST":
        password = request.form.get("password")
        confirm = request.form.get("confirm")
        if not (password and confirm):
            error = "Заполните все поля"
        elif password != confirm:
            error = "Пароли не совпадают"
        else:
            user["password"] = password
            reset_codes.pop(phone, None)
            flash("Пароль успешно изменён!", "success")
            return redirect(url_for("login_page"))
    return render_template("reset_password.html", phone=phone, error=error)

@app.route("/edit_profile", methods=["GET", "POST"])
def edit_profile():
    user = get_current_user()
    if not user:
        return redirect(url_for("login_page"))
    error = None
    if request.method == "POST":
        name = request.form.get("name")
        phone = request.form.get("phone")
        # Add password and confirm password fields to edit profile
        password = request.form.get("password")
        confirm = request.form.get("confirm")
        if not (name and phone):
            error = "Заполните все поля"
        elif password and password != confirm:
            error = "Пароли не совпадают"
        else:
            user["name"] = name
            user["phone"] = phone
            if password:
                user["password"] = password # Update password if provided
            if "avatar" in request.files:
                file = request.files["avatar"]
                if file and allowed_file(file.filename):
                    ext = file.filename.rsplit(".", 1)[1].lower()
                    avatar = f"{uuid.uuid4()}.{ext}"
                    file.save(os.path.join(AVATAR_FOLDER, avatar))
                    user["avatar"] = avatar
            save_users() # Save users after profile update
            flash("Профиль обновлён!", "success")
            return redirect(url_for("profile_page"))
    return render_template("edit_profile.html", user=user, error=error)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True) 