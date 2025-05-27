# Telegram Multi-Account Userbot Manager & Reporter (مدیریت چند اکانت یوزربات تلگرام و گزارشگر)

This is a Telegram bot built with Python and Telethon that allows users to manage multiple Telegram user accounts (userbots) and perform actions such as reporting targets using all managed accounts. Sessions are stored in an SQLite database.

این یک ربات تلگرامی است که با پایتون و کتابخانه Telethon ساخته شده است. این ربات به کاربران امکان مدیریت چندین اکانت کاربری تلگرام (یوزربات) و انجام اقداماتی مانند گزارش دادن اهداف با استفاده از تمام اکانت‌های مدیریت شده را می‌دهد. نشست‌ها (sessions) در یک پایگاه داده SQLite ذخیره می‌شوند.

---

## English

### 🌟 Features

*   **Multi-Account Management**: Add and manage multiple Telegram user accounts.
*   **Secure Session Storage**: User sessions are stored securely in an SQLite database.
*   **Login Flow**:
    *   Add accounts via phone number.
    *   Handles OTP code verification (via inline keyboard).
    *   Supports 2FA (Two-Factor Authentication) password entry.
*   **Account Listing**: View all your added userbot accounts.
*   **Logout**: Remove specific userbot accounts.
*   **Multi-Account Reporting**:
    *   Set a default report message.
    *   Report a target (user, channel, group) using all your logged-in accounts with a specified reason.
    *   Supported report reasons: `spam`, `violence`, `pornography`, `childabuse`, `copyright`, `geoirrelevant`, `fake`, `other`.
*   **Farsi & English Interface**: Help and command descriptions available in Farsi.

###  Prerequisites

*   Python 3.10 or higher
*   A Telegram API ID and API Hash (get these from [my.telegram.org](https://my.telegram.org/apps))
*   A Telegram Bot Token (get this from [@BotFather](https://t.me/BotFather))

### 🛠️ Setup Instructions

1.  **Clone the Repository**:
    ```bash
    git clone <your-repository-url>
    cd <repository-name>
    ```

2.  **Create a Virtual Environment (Recommended)**:
    ```bash
    python -m venv myenv
    source myenv/bin/activate  # On Windows: myenv\Scripts\activate
    ```

3.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
    The `requirements.txt` should include:
    ```
    telethon
    sqlalchemy
    aiosqlite
    python-dotenv
    ```

4.  **Set Environment Variables**:
    Create a `.env` file in the root directory of the project and add your credentials:
    ```env
    API_ID=1234567
    API_HASH=your_api_hash
    BOT_TOKEN=your_bot_token
    # DATABASE_URL=sqlite+aiosqlite:///./sessions.db # This is the default
    ```
    Replace `1234567`, `your_api_hash`, and `your_bot_token` with your actual values. `DATABASE_URL` is optional if you're using the default SQLite database named `sessions.db`.

5.  **Database Initialization**:
    The bot will automatically create the `sessions.db` SQLite database file and the necessary tables (`user_sessions`, `report_settings`) on its first run if they don't exist.

### 🚀 Running the Bot

Execute the `main.py` script:
```bash
python main.py
```
The bot should start, and you will see log messages in your console. You can then interact with your bot on Telegram.

### 🤖 Bot Commands

*   `/start` - Start interacting with the bot and see available commands.
*   `/add` - Add a new userbot account.
*   `/my_accounts` - List all your added userbot accounts.
*   `/logout <phone_number>` - Log out and remove a specific userbot account (e.g., `/logout +1234567890`).
*   `/set_report_message <message>` - Set your default message for reports (e.g., `/set_report_message This user is violating terms.`).
*   `/report <target> <reason>` - Report a target with all your accounts (e.g., `/report @username spam`).
    *   Target can be a username (`@username`), user ID, chat ID, or a public channel/group link.
    *   Available reasons: `spam`, `violence`, `porn`, `childabuse`, `copyright`, `geo`, `fake`, `other`.
*   `/cancel` - Cancel the current ongoing operation (like adding an account).
*   `/help` - Show help information.

---

## فارسی (Farsi)

### 🌟 ویژگی‌ها

*   **مدیریت چند اکانت**: افزودن و مدیریت چندین اکانت کاربری تلگرام.
*   **ذخیره‌سازی امن نشست‌ها**: نشست‌های کاربری به طور امن در پایگاه داده SQLite ذخیره می‌شوند.
*   **فرآیند ورود**:
    *   افزودن اکانت از طریق شماره تلفن.
    *   پشتیبانی از تایید کد یکبار مصرف (از طریق کیبورد داخلی تلگرام).
    *   پشتیبانی از ورود با رمز عبور تایید دو مرحله‌ای (2FA).
*   **لیست اکانت‌ها**: مشاهده تمام اکانت‌های یوزربات اضافه شده توسط شما.
*   **خروج از حساب**: حذف یک اکانت یوزربات مشخص.
*   **گزارش با چند اکانت**:
    *   تنظیم یک پیام گزارش پیش‌فرض.
    *   گزارش یک هدف (کاربر، کانال، گروه) با استفاده از تمام اکانت‌های متصل شما و با دلیل مشخص.
    *   دلایل گزارش پشتیبانی شده: `spam` (هرزنامه)، `violence` (خشونت)، `porn` (محتوای بزرگسالان)، `childabuse` (کودک آزاری)، `copyright` (نقض کپی‌رایت)، `geo` (موقعیت نامربوط)، `fake` (جعلی)، `other` (سایر موارد).
*   **رابط کاربری فارسی و انگلیسی**: توضیحات دستورات و راهنما به زبان فارسی موجود است.

###  پیش‌نیازها

*   پایتون 3.10 یا بالاتر
*   شناسه API (API ID) و هش API (API Hash) تلگرام (قابل دریافت از [my.telegram.org](https://my.telegram.org/apps))
*   توکن ربات تلگرام (قابل دریافت از [@BotFather](https://t.me/BotFather))

### 🛠️ راهنمای نصب و راه‌اندازی

1.  **دریافت پروژه (Clone)**:
    ```bash
    git clone <your-repository-url>
    cd <repository-name>
    ```

2.  **ایجاد محیط مجازی (توصیه می‌شود)**:
    ```bash
    python -m venv myenv
    source myenv/bin/activate  # در ویندوز: myenv\Scripts\activate
    ```

3.  **نصب نیازمندی‌ها**:
    ```bash
    pip install -r requirements.txt
    ```
    فایل `requirements.txt` باید شامل موارد زیر باشد:
    ```
    telethon
    sqlalchemy
    aiosqlite
    python-dotenv
    ```

4.  **تنظیم متغیرهای محیطی**:
    یک فایل با نام `.env` در پوشه اصلی پروژه ایجاد کرده و اطلاعات خود را وارد کنید:
    ```env
    API_ID=1234567
    API_HASH=your_api_hash
    BOT_TOKEN=your_bot_token
    # DATABASE_URL=sqlite+aiosqlite:///./sessions.db # این مقدار پیش‌فرض است
    ```
    مقادیر `1234567`، `your_api_hash` و `your_bot_token` را با اطلاعات واقعی خود جایگزین کنید. اگر از پایگاه داده SQLite پیش‌فرض با نام `sessions.db` استفاده می‌کنید، تنظیم `DATABASE_URL` اختیاری است.

5.  **آماده‌سازی پایگاه داده**:
    ربات به طور خودکار فایل پایگاه داده SQLite با نام `sessions.db` و جداول مورد نیاز (`user_sessions`, `report_settings`) را در اولین اجرا، در صورت عدم وجود، ایجاد خواهد کرد.

### 🚀 اجرای ربات

فایل `main.py` را اجرا کنید:
```bash
python main.py
```
ربات شروع به کار کرده و پیام‌های مربوط به اجرا را در کنسول خود مشاهده خواهید کرد. سپس می‌توانید با ربات خود در تلگرام تعامل داشته باشید.

### 🤖 دستورات ربات

*   `/start` - شروع تعامل با ربات و مشاهده دستورات موجود.
*   `/add` - افزودن یک اکانت یوزربات جدید.
*   `/my_accounts` - نمایش لیست تمام اکانت‌های یوزربات اضافه شده توسط شما.
*   `/logout <شماره_تلفن>` - خروج و حذف یک اکانت یوزربات مشخص (مثال: `/logout +989123456789`).
*   `/set_report_message <پیام>` - تنظیم پیام پیش‌فرض برای گزارش‌ها (مثال: `/set_report_message این کاربر قوانین را نقض کرده است.`).
*   `/report <هدف> <دلیل>` - گزارش یک هدف با تمام اکانت‌های شما (مثال: `/report @username spam`).
    *   هدف می‌تواند نام کاربری (`@username`)، شناسه کاربری، شناسه چت، یا لینک عمومی کانال/گروه باشد.
    *   دلایل موجود: `spam`, `violence`, `porn`, `childabuse`, `copyright`, `geo`, `fake`, `other`.
*   `/cancel` - لغو عملیات در حال انجام (مانند افزودن اکانت).
*   `/help` - نمایش پیام راهنما.

---

### 🤝 Contributing (مشارکت)

Contributions are welcome! Please feel free to submit a pull request or open an issue.
از مشارکت شما استقبال می‌شود! لطفاً در صورت تمایل، یک پول ریکوئست (pull request) ارسال کرده یا یک ایشو (issue) باز کنید.

### 📄 License (مجوز)

This project is licensed under the MIT License. See the `LICENSE` file for details (if available).
این پروژه تحت مجوز MIT منتشر شده است. برای جزئیات بیشتر به فایل `LICENSE` (در صورت وجود) مراجعه کنید. # Telegram-reporter
# telegramreporter
