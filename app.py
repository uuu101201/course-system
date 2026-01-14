from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import calendar

# ------------------------------
# Flask 基本設定
# ------------------------------
app = Flask(__name__)

# Session 需要 secret_key（正式上線請改成更複雜）
app.secret_key = "change_this_secret_key"

# SQLite 資料庫設定（檔案會在專案根目錄生成 courses.db）
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///courses.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ------------------------------
# 管理者帳密（正式上線請改掉）
# ------------------------------
ADMIN_ACCOUNT = "admin"
ADMIN_PASSWORD = "1234"

# ------------------------------
# 資料表：課程
# ------------------------------
class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # 日期：YYYY-MM-DD，例如 2026-01-20
    course_date = db.Column(db.String(10), nullable=False)

    # 時間：HH:MM，例如 14:00
    course_time = db.Column(db.String(5), nullable=False)

    # 課程名稱
    course_name = db.Column(db.String(50), nullable=False)

    # 名額上限、剩餘名額
    capacity = db.Column(db.Integer, nullable=False)
    remaining = db.Column(db.Integer, nullable=False)

# ------------------------------
# 資料表：報名
# ------------------------------
class Registration(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # 對應課程 ID（簡化版：不做外鍵也能跑）
    course_id = db.Column(db.Integer, nullable=False)

    # 學員資料
    name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), nullable=False)

# ------------------------------
# 首頁：月曆顯示（含月份切換 + 上午/下午顏色 + 同日排序）
# ------------------------------
@app.route("/")
def index():
    # 取得網址列 ?month=YYYY-MM，例如 2026-01
    month_str = request.args.get("month")

    # 若未指定月份，使用今天年月
    if month_str:
        year, month = map(int, month_str.split("-"))
    else:
        today = datetime.today()
        year, month = today.year, today.month
        month_str = f"{year}-{month:02d}"

    # 產生月曆格子（list of weeks）
    cal = calendar.monthcalendar(year, month)

    # 撈出該月份所有課程（用 startswith 篩選 YYYY-MM）
    courses = Course.query.filter(Course.course_date.startswith(month_str)).all()

    # 將課程依日期分組：course_dict[day] = [課程, 課程...]
    course_dict = {}

    for c in courses:
        # 取出 day（1~31）
        day = int(c.course_date.split("-")[2])

        # 判斷上午/下午，用於前端套不同顏色
        hour = int(c.course_time.split(":")[0])
        c.session_type = "morning" if hour < 12 else "afternoon"

        course_dict.setdefault(day, []).append(c)

    # ⭐ 同一天的課程依時間排序（09:00 < 14:00）
    for day in course_dict:
        course_dict[day].sort(key=lambda x: x.course_time)

    return render_template(
        "calendar.html",
        cal=cal,
        year=year,
        month=month,
        courses=course_dict,
        month_str=month_str
    )

# ------------------------------
# 報名頁：GET 顯示表單 / POST 送出報名
# ------------------------------
@app.route("/register/<int:course_id>", methods=["GET", "POST"])
def register(course_id):
    course = Course.query.get(course_id)

    # 課程不存在
    if not course:
        return "課程不存在"

    # 額滿就鎖定
    if course.remaining <= 0:
        return "此課程已額滿"

    if request.method == "POST":
        # 再次檢查（避免多人同時送出導致負數）
        course = Course.query.get(course_id)
        if course.remaining <= 0:
            return "此課程已額滿"

        # 建立報名資料
        reg = Registration(
            course_id=course.id,
            name=request.form["name"],
            email=request.form["email"],
            phone=request.form["phone"]
        )

        # 名額 -1
        course.remaining -= 1

        db.session.add(reg)
        db.session.commit()

        # 回月曆
        return redirect("/")

    return render_template("register.html", course=course)

# ------------------------------
# 管理者登入
# ------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        acc = request.form["account"]
        pwd = request.form["password"]

        if acc == ADMIN_ACCOUNT and pwd == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/admin")
        else:
            return "帳號或密碼錯誤"

    return render_template("login.html")

# ------------------------------
# 管理者登出
# ------------------------------
@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect("/")

# ------------------------------
# 管理後台：查看報名名單
# ------------------------------
@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/login")

    courses = Course.query.order_by(Course.course_date, Course.course_time).all()
    return render_template("admin.html", courses=courses, Registration=Registration)

# ------------------------------
# 新增課程（後台）
# ------------------------------
@app.route("/admin/add", methods=["GET", "POST"])
def add_course():
    if not session.get("admin"):
        return redirect("/login")

    if request.method == "POST":
        date = request.form["date"]      # YYYY-MM-DD
        time = request.form["time"]      # HH:MM
        name = request.form["name"]
        cap = int(request.form["capacity"])

        new_course = Course(
            course_date=date,
            course_time=time,
            course_name=name,
            capacity=cap,
            remaining=cap
        )

        db.session.add(new_course)
        db.session.commit()
        return redirect("/admin")

    return render_template("add_course.html")

# ------------------------------
# 刪除課程（後台）
# - 會連同該課程的所有報名一起刪除
# - 使用 POST 避免被網址誤刪
# ------------------------------
@app.route("/admin/delete/<int:course_id>", methods=["POST"])
def delete_course(course_id):
    if not session.get("admin"):
        return redirect("/login")

    course = Course.query.get(course_id)
    if not course:
        return "課程不存在"

    # 先刪除該課程所有報名資料
    Registration.query.filter_by(course_id=course_id).delete()

    # 再刪課程
    db.session.delete(course)
    db.session.commit()

    return redirect("/admin")
# ------------------------------
# 程式啟動時，確保資料表存在
# （本機 + Render 都會執行）
# ------------------------------
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run()
