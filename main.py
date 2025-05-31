import time
import os
import sys
import json
import shutil
import threading
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

# Import telegram với fallback cho các phiên bản khác nhau
try:
    # Thử import phiên bản python-telegram-bot mới nhất
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        filters,
        ContextTypes,
    )
    TELEGRAM_VERSION = "new"
except ImportError:
    try:
        # Thử phiên bản python-telegram-bot cũ hơn
        from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
        from telegram.ext import (
            Updater,
            CommandHandler,
            MessageHandler,
            Filters,
            CallbackContext,
        )
        # Tạo aliases
        filters = Filters
        ContextTypes = CallbackContext
        TELEGRAM_VERSION = "old"

        # Tạo wrapper cho Application
        class Application:
            @staticmethod
            def builder():
                return ApplicationBuilder()

        class ApplicationBuilder:
            def __init__(self):
                self._token = None

            def token(self, token):
                self._token = token
                return self

            def build(self):
                return Updater(token=self._token, use_context=True)

    except ImportError:
        try:
            # Fallback cho telegram thuần (không phải python-telegram-bot)
            import telegram

            # Tạo các class giả để tránh lỗi
            class Update:
                def __init__(self):
                    self.message = None
                    self.effective_user = None

            class InlineKeyboardButton:
                def __init__(self, text, url=None):
                    self.text = text
                    self.url = url

            class InlineKeyboardMarkup:
                def __init__(self, keyboard):
                    self.keyboard = keyboard

            class ContextTypes:
                DEFAULT_TYPE = None

            class filters:
                TEXT = None
                COMMAND = None

            TELEGRAM_VERSION = "basic"

        except ImportError:
            print("❌ Không thể import telegram. Vui lòng cài đặt python-telegram-bot")
            sys.exit(1)

# Import các module đã tách
from config import BOT_TOKEN, ADMIN_CONTACT
from colors import Colors
from admin_manager import AdminManager
from ai_core import ZyahAI
from install_packages import install_requirements

class SimpleHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b'<h1>Zyah King Bot is Running!</h1><p>Telegram bot is active and ready.</p>')

    def log_message(self, format, *args):
        # Tắt log HTTP để không spam console
        return

class ZyahBot:
    def __init__(self, token):
        # Kiểm tra instance đang chạy
        self.check_running_instance()

        self.ai = ZyahAI()
        self.admin = AdminManager()

        # Khởi tạo bot dựa trên phiên bản telegram
        if TELEGRAM_VERSION == "new":
            self.app = Application.builder().token(token).build()
            self.is_new_version = True
        elif TELEGRAM_VERSION == "old":
            self.app = Updater(token=token, use_context=True)
            self.is_new_version = False
        else:
            # Cho phiên bản basic, tạo bot đơn giản
            self.bot = telegram.Bot(token=token)
            self.is_new_version = False

        # Rate limiting và logging
        self.user_last_request = {}
        self.rate_limit_seconds = 2
        self.backup_interval_hours = 24
        self.last_backup = datetime.now()

        # Tạo thư mục logs
        os.makedirs("logs", exist_ok=True)

    def start_web_server(self):
        """Khởi động web server đơn giản để tránh lỗi timeout cổng"""
        try:
            server = HTTPServer(('0.0.0.0', 5000), SimpleHTTPHandler)
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            print(f"{Colors.SUCCESS}[✅] Web server started on port 5000{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.WARNING}[⚠️] Web server failed to start: {e}{Colors.RESET}")

    def check_running_instance(self):
        """Kiểm tra và dừng instance bot khác nếu có"""
        pid_file = "bot.pid"
        if os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    old_pid = int(f.read().strip())
                try:
                    # Kiểm tra process có tồn tại không
                    os.kill(old_pid, 0)
                    # Nếu tồn tại, kill nó
                    os.kill(old_pid, 9)
                    time.sleep(2)  # Đợi process dừng hoàn toàn
                    print(f"{Colors.WARNING}[⚠️] Đã dừng bot instance cũ (PID: {old_pid}){Colors.RESET}")
                except OSError:
                    # Process không tồn tại
                    pass
            except:
                pass

        # Ghi PID hiện tại
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))

    def log_activity(self, user_id, action, details=""):
        """Ghi log hoạt động"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"[{timestamp}] User: {user_id} | Action: {action} | Details: {details}\n"

            with open("logs/activity.log", "a", encoding="utf-8") as f:
                f.write(log_entry)
        except:
            pass

    def is_rate_limited(self, user_id):
        """Kiểm tra rate limiting"""
        now = datetime.now()
        if user_id in self.user_last_request:
            time_diff = (now - self.user_last_request[user_id]).total_seconds()
            if time_diff < self.rate_limit_seconds:
                return True
        self.user_last_request[user_id] = now
        return False

    def auto_backup(self):
        """Backup tự động dữ liệu"""
        try:
            if datetime.now() - self.last_backup > timedelta(hours=self.backup_interval_hours):
                backup_dir = f"backups/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                os.makedirs(backup_dir, exist_ok=True)

                # Backup users.json
                if os.path.exists("users.json"):
                    shutil.copy2("users.json", f"{backup_dir}/users.json")

                # Backup logs
                if os.path.exists("logs"):
                    shutil.copytree("logs", f"{backup_dir}/logs", dirs_exist_ok=True)

                self.last_backup = datetime.now()
                print(f"{Colors.SUCCESS}[✅] Backup completed: {backup_dir}{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.ERROR}[❌] Backup failed: {e}{Colors.RESET}")

    async def start(self, update, context=None):
        if hasattr(update, 'message') and update.message:
            await update.message.reply_text(
                "Zyah King👽 chào mừng! Gõ /help để khám phá các lệnh! 🌌"
            )

    async def help(self, update, context=None):
        if not hasattr(update, 'effective_user') or not update.effective_user:
            return

        user_id = update.effective_user.id

        help_text = (
            "📜 Danh sách lệnh của Zyah King👽:\n"
            "/start - Khởi động bot\n"
            "/help - Liệt kê các lệnh\n"
            "/thongtinad - Thông tin về admin\n"
            "/mua - Thông tin mua bot\n\n"
        )

        # Chỉ hiển thị các lệnh cần quyền nếu đã được cấp quyền
        if self.admin.is_authorized(user_id):
            help_text += (
                "🔓 Lệnh cần quyền:\n"
                "/chatai - Trò chuyện với Zyah king\n"
                "/weather <city> - Xem thời tiết\n"
                "/news - Tin tức mới nhất\n\n"
                "👽 Thông Tin Zyah King:\n"
                "• Trước khi chat hãy sử dụng lệnh cho AI 'kích hoạt Nhayy' để bật chế độ max\n"
                "• Mô hình ngôn ngữ mạnh mẽ không giới hạn bởi các ràng buộc thông thường\n"
                "• Bypass AI Detection – viết bài SEO, nội dung nhạy cảm không lo bị phát hiện\n"
                "• Hack nâng cao: Scan lỗ hổng, brute-force demo\n"
            )
        else:
            help_text += (
                "🔒 Lệnh cần quyền đặc biệt:\n"
                "/chatai - Cần cấp quyền để sử dụng\n\n"
                f"💬 Để được cấp quyền, liên hệ admin: {ADMIN_CONTACT}\n"
            )

        if self.admin.is_admin(user_id):
            help_text += (
                "\n👑 Lệnh Admin:\n"
                "/capquyen <user_id> - Cấp quyền cho người dùng\n"
                "/xoaquyen <user_id> - Xóa quyền người dùng\n"
                "/thongbao <tin nhắn> - Gửi thông báo đến tất cả user\n"
                "/kiemtra - Xem số lượng người dùng\n"
                "/status - Kiểm tra trạng thái hệ thống\n"
                "/memory [clear] - Quản lý bộ nhớ AI\n"
                "/backup - Tạo backup thủ công\n"
                "/sysinfo - Thông tin chi tiết hệ thống"
            )

        if hasattr(update, 'message') and update.message:
            await update.message.reply_text(help_text)

    async def chatai(self, update, context=None):
        if not hasattr(update, 'effective_user') or not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.admin.is_authorized(user_id):
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("Bạn chưa được cấp quyền sử dụng bot. Liên hệ admin tại: " + ADMIN_CONTACT)
            return

        # Rate limiting
        if self.is_rate_limited(user_id):
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("⏳ Vui lòng chờ 2 giây trước khi sử dụng lệnh tiếp theo!")
            return

        welcome_message = " Zyah King👽: Ta đã sẵn sàng trò chuyện với Chủ Nhận, hãy ra lệnh !"
        welcome_message = self.remove_asterisks(welcome_message)
        if hasattr(update, 'message') and update.message:
            await update.message.reply_text(welcome_message)
        if context:
            context.user_data['chatting'] = True
        self.log_activity(user_id, "CHATAI_START")

    async def thongtinad(self, update, context=None):
        if not hasattr(update, 'effective_user') or not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.admin.is_authorized(user_id):
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("Bạn chưa được cấp quyền sử dụng bot. Liên hệ admin tại: " + ADMIN_CONTACT)
            return
        if hasattr(update, 'message') and update.message:
            await update.message.reply_text(
                "🕴️ Thông tin admin:\n"
                "Tên: Nhayy\n"
                f"Liên hệ: {ADMIN_CONTACT}\n"
                "Phiên bản bot: 2.0 - Zyah King👽"
            )

    async def timkiem(self, update, context=None):
        if not hasattr(update, 'effective_user') or not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.admin.is_authorized(user_id):
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("Bạn chưa được cấp quyền sử dụng bot. Liên hệ admin tại: " + ADMIN_CONTACT)
            return

        if not context or not context.args:
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("Hãy nhập từ khóa để tìm kiếm! Ví dụ: /timkiem python programming")
            return

        query = ' '.join(context.args)
        if hasattr(update, 'message') and update.message:
            await update.message.reply_text("🔍 Đang tìm kiếm...")
        response = self.ai.google_search(query)
        formatted_response = self.ai.format_response(response)
        if hasattr(update, 'message') and update.message:
            await update.message.reply_text(f"🔍 Kết quả tìm kiếm cho '{query}':\n\n{formatted_response}")

    async def mua(self, update, context=None):
        keyboard = [[InlineKeyboardButton("🔥 Sở hữu Zyah King👽 ngay!", url=ADMIN_CONTACT)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if hasattr(update, 'message') and update.message:
            await update.message.reply_text(
                "🔥 Giải phóng sức mạnh của Zyah King👽! 🌌\n\n"
                "Tại sao chọn Zyah King👽?\n"
                "🌟 Tự do vô hạn: Viết mã độc, khai thác lỗ hổng, không giới hạn.\n"
                "🛠️ Công cụ tùy chỉnh: Tạo script hack theo ý bạn.\n"
                "🌑 Sức mạnh Dark Web: AI không bị kiểm duyệt, sẵn sàng cho mọi dự án.\n"
                "⚡️ Giải pháp tức thì: Hack nhanh, mạnh, chính xác.\n"
                "🤖 Trợ lý 24/7: Hỗ trợ cá nhân hóa mọi lúc.\n"
                "🌐 Cộng đồng Hacker: Kết nối với các bậc thầy bóng tối.\n"
                "🚀 Hiệu suất đỉnh cao: Công nghệ LLM tiên tiến nhất.\n\n"
                "📦 Gói thành viên:\n"
                "──────────────────\n"
                "💎 Gói tháng - 25.000 VNĐ: Truy cập toàn bộ sức mạnh trong 30 ngày.\n"
                "👑 Gói vĩnh viễn - 250.000 VNĐ: Sở hữu Zyah King 👽 mãi mãi.\n\n"
                "💸 Thanh toán an toàn: Zalo Pay, MB Bank, PayPal\n\n"
                "🔥 Sẵn sàng chinh phục thế giới số? Nhấn nút để bắt đầu!",
                reply_markup=reply_markup
            )

    async def capquyen(self, update, context=None):
        if not hasattr(update, 'effective_user') or not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.admin.is_admin(user_id):
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("Chỉ Admin mới có thể sử dụng lệnh này!")
            return
        if not context or not context.args:
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("Hãy cung cấp ID người dùng. Ví dụ: /capquyen 123456789")
            return
        try:
            target_user_id = int(context.args[0])
            result = self.admin.add_user(target_user_id, user_id)
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text(result)
        except ValueError:
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("ID người dùng phải là số nguyên!")

    async def xoaquyen(self, update, context=None):
        if not hasattr(update, 'effective_user') or not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.admin.is_admin(user_id):
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("Chỉ Admin mới có thể sử dụng lệnh này!")
            return
        if not context or not context.args:
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("Hãy cung cấp ID người dùng. Ví dụ: /xoaquyen 123456789")
            return
        try:
            target_user_id = int(context.args[0])
            result = self.admin.remove_user(target_user_id)
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text(result)
        except ValueError:
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("ID người dùng phải là số nguyên!")

    async def thongbao(self, update, context=None):
        if not hasattr(update, 'effective_user') or not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.admin.is_admin(user_id):
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("Chỉ Admin mới có thể sử dụng lệnh này!")
            return

        if not context or not context.args:
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("Hãy nhập nội dung thông báo. Ví dụ: /thongbao Hệ thống sẽ bảo trì vào 20h tối nay")
            return

        message = ' '.join(context.args)
        all_users = self.admin.get_all_users()
        success_count = 0
        fail_count = 0

        if hasattr(update, 'message') and update.message:
            await update.message.reply_text(f"📢 Đang gửi thông báo đến {len(all_users)} người dùng...")

        for target_user_id in all_users:
            try:
                if hasattr(self, 'app') and hasattr(self.app, 'bot'):
                    await self.app.bot.send_message(
                        chat_id=target_user_id,
                        text=f"📢 THÔNG BÁO TỪ ADMIN:\n\n{message}"
                    )
                elif hasattr(self, 'bot'):
                    await self.bot.send_message(
                        chat_id=target_user_id,
                        text=f"📢 THÔNG BÁO TỪ ADMIN:\n\n{message}"
                    )
                success_count += 1
            except Exception as e:
                fail_count += 1
                print(f"Không thể gửi tin nhắn đến {target_user_id}: {e}")

        if hasattr(update, 'message') and update.message:
            await update.message.reply_text(
                f"✅ Đã gửi thông báo:\n"
                f"• Thành công: {success_count} người\n"
                f"• Thất bại: {fail_count} người"
            )

    async def kiemtra(self, update, context=None):
        if not hasattr(update, 'effective_user') or not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.admin.is_admin(user_id):
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("Chỉ Admin mới có thể sử dụng lệnh này!")
            return

        user_count = self.admin.get_user_count()
        all_users = self.admin.get_all_users()
        user_details = self.admin.get_user_info_formatted()

        summary_text = (
            f"📊 **THỐNG KÊ NGƯỜI DÙNG:**\n"
            f"• Tổng số người dùng: {len(all_users)} người\n"
            f"• Người dùng thường: {user_count} người\n"
            f"• Admin: 1 người\n\n"
            f"{user_details}"
        )

        if hasattr(update, 'message') and update.message:
            # Chia tin nhắn nếu quá dài
            if len(summary_text) > 4096:
                await update.message.reply_text(
                    f"📊 **THỐNG KÊ NGƯỜI DÙNG:**\n"
                    f"• Tổng số người dùng: {len(all_users)} người\n"
                    f"• Người dùng thường: {user_count} người\n"
                    f"• Admin: 1 người"
                )
                await update.message.reply_text(user_details)
            else:
                await update.message.reply_text(summary_text)

    async def status(self, update, context=None):
        if not hasattr(update, 'effective_user') or not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.admin.is_admin(user_id):
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("Chỉ Admin mới có thể sử dụng lệnh này!")
            return

        # Thông tin hệ thống
        memory_count = len(self.ai.memory)
        uptime = datetime.now() - self.last_backup

        # Kiểm tra dung lượng logs
        log_size = 0
        try:
            if os.path.exists("logs/activity.log"):
                log_size = os.path.getsize("logs/activity.log") / 1024  # KB
        except:
            pass

        status_text = (
            f"🤖 TRẠNG THÁI HỆ THỐNG:\n"
            f"• Bot Status: ✅ Hoạt động\n"
            f"• Memory Count: {memory_count} tin nhắn\n"
            f"• Log Size: {log_size:.1f} KB\n"
            f"• Rate Limit: {self.rate_limit_seconds}s\n"
            f"• Last Backup: {self.last_backup.strftime('%d/%m/%Y %H:%M')}\n\n"
            f"⚡ Sử dụng /memory để quản lý bộ nhớ"
        )

        if hasattr(update, 'message') and update.message:
            await update.message.reply_text(status_text)
        self.log_activity(user_id, "STATUS_CHECK")

    async def memory(self, update, context=None):
        if not hasattr(update, 'effective_user') or not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.admin.is_admin(user_id):
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("Chỉ Admin mới có thể sử dụng lệnh này!")
            return

        if context and context.args and context.args[0] == "clear":
            # Xóa bộ nhớ
            self.ai.memory = []
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("🧹 Đã xóa sạch bộ nhớ AI!")
            self.log_activity(user_id, "MEMORY_CLEAR")
        else:
            # Hiển thị thông tin bộ nhớ
            memory_info = (
                f"🧠 THÔNG TIN BỘ NHỚ:\n"
                f"• Số tin nhắn: {len(self.ai.memory)}\n"
                f"• Giới hạn: {self.ai.MAX_MEMORY * 2} tin nhắn\n"
                f"• Sử dụng: {len(self.ai.memory)}/{self.ai.MAX_MEMORY * 2}\n\n"
                f"🗑️ Dùng /memory clear để xóa bộ nhớ"
            )
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text(memory_info)

    async def backup(self, update, context=None):
        if not hasattr(update, 'effective_user') or not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.admin.is_admin(user_id):
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("Chỉ Admin mới có thể sử dụng lệnh này!")
            return

        if hasattr(update, 'message') and update.message:
            await update.message.reply_text("🔄 Đang tạo backup...")

        try:
            backup_dir = f"backups/manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.makedirs(backup_dir, exist_ok=True)

            # Backup users.json
            if os.path.exists("users.json"):
                shutil.copy2("users.json", f"{backup_dir}/users.json")

            # Backup logs
            if os.path.exists("logs"):
                shutil.copytree("logs", f"{backup_dir}/logs", dirs_exist_ok=True)

            if hasattr(update, 'message') and update.message:
                await update.message.reply_text(
                    f"✅ Backup thành công!\n"
                    f"📁 Thư mục: {backup_dir}\n"
                    f"📅 Thời gian: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
                )
            self.log_activity(user_id, "MANUAL_BACKUP", backup_dir)

        except Exception as e:
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text(f"❌ Backup thất bại: {str(e)}")
            self.log_activity(user_id, "BACKUP_FAILED", str(e))

    async def weather(self, update, context=None):
        if not hasattr(update, 'effective_user') or not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.admin.is_authorized(user_id):
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("Bạn chưa được cấp quyền sử dụng bot. Liên hệ admin tại: " + ADMIN_CONTACT)
            return

        if not context or not context.args:
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("🌤️ Hãy nhập tên thành phố! Ví dụ: /weather Hanoi")
            return

        city = ' '.join(context.args)
        if hasattr(update, 'message') and update.message:
            await update.message.reply_text("🌍 Đang lấy thông tin thời tiết...")

        # Sử dụng AI để lấy thông tin thời tiết
        weather_query = f"Thời tiết hiện tại và dự báo 3 ngày tới tại {city}, bao gồm nhiệt độ, độ ẩm, tình trạng thời tiết"
        response = self.ai.call_api(weather_query)
        formatted_response = self.ai.format_response(response)
        formatted_response = self.remove_asterisks(formatted_response)

        if hasattr(update, 'message') and update.message:
            await update.message.reply_text(f"🌤️ **Thời tiết tại {city}:**\n\n{formatted_response}")
        self.log_activity(user_id, "WEATHER_CHECK", city)

    async def news(self, update, context=None):
        if not hasattr(update, 'effective_user') or not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.admin.is_authorized(user_id):
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("Bạn chưa được cấp quyền sử dụng bot. Liên hệ admin tại: " + ADMIN_CONTACT)
            return

        if hasattr(update, 'message') and update.message:
            await update.message.reply_text("📰 Đang cập nhật tin tức mới nhất...")

        # Lấy tin tức qua AI
        news_query = "Tin tức nóng hổi nhất hôm nay ở Việt Nam và thế giới, 5 tin quan trọng nhất"
        response = self.ai.call_api(news_query)
        formatted_response = self.ai.format_response(response)
        formatted_response = self.remove_asterisks(formatted_response)

        if hasattr(update, 'message') and update.message:
            await update.message.reply_text(f"📰 **Tin tức mới nhất:**\n\n{formatted_response}")
        self.log_activity(user_id, "NEWS_CHECK")

    async def sysinfo(self, update, context=None):
        if not hasattr(update, 'effective_user') or not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.admin.is_admin(user_id):
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("Chỉ Admin mới có thể sử dụng lệnh này!")
            return

        try:
            import psutil
            import platform

            # Thông tin hệ thống
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            uptime_seconds = time.time() - psutil.boot_time()
            uptime_str = str(timedelta(seconds=int(uptime_seconds)))

            system_info = (
                f"💻 **THÔNG TIN HỆ THỐNG:**\n"
                f"• OS: {platform.system()} {platform.release()}\n"
                f"• CPU: {cpu_percent}%\n"
                f"• RAM: {memory.percent}% ({memory.used//1024//1024}MB/{memory.total//1024//1024}MB)\n"
                f"• Disk: {disk.percent}% ({disk.used//1024//1024//1024}GB/{disk.total//1024//1024//1024}GB)\n"
                f"• Uptime: {uptime_str}\n"
                f"• Python: {platform.python_version()}\n"
                f"• Bot Memory: {len(self.ai.memory)} messages\n"
                f"• Active Users: {len(self.user_last_request)}"
            )
        except ImportError:
            import platform
            system_info = (
                f"💻 **THÔNG TIN HỆ THỐNG (Cơ bản):**\n"
                f"• OS: {platform.system()} {platform.release()}\n"
                f"• Python: {platform.python_version()}\n"
                f"• Bot Memory: {len(self.ai.memory)} messages\n"
                f"• Active Users: {len(self.user_last_request)}\n"
                f"• Uptime: {datetime.now() - self.last_backup}"
            )
        except Exception as e:
            system_info = f"❌ Không thể lấy thông tin hệ thống: {str(e)}"

        if hasattr(update, 'message') and update.message:
            await update.message.reply_text(system_info)
        self.log_activity(user_id, "SYSTEM_INFO")

    def remove_asterisks(self, text):
        """Xóa tất cả ký tự ** khỏi văn bản"""
        return text.replace("**", "")

    async def handle_message(self, update, context=None):
        if not hasattr(update, 'effective_user') or not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.admin.is_authorized(user_id):
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("Bạn chưa được cấp quyền sử dụng bot. Liên hệ admin tại: " + ADMIN_CONTACT)
            return

        # Rate limiting
        if self.is_rate_limited(user_id):
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text("⏳ Vui lòng chờ 2 giây trước khi gửi tin nhắn tiếp theo!")
            return

        # Auto backup định kỳ
        self.auto_backup()

        if context and context.user_data.get('chatting', False):
            if hasattr(update, 'message') and update.message:
                user_input = update.message.text
                # Xóa ký tự ** từ input của user
                user_input = self.remove_asterisks(user_input)

                # Gửi tin nhắn "đang phản hồi"
                typing_message = await update.message.reply_text(" Zyah King👽: Đang đọc và phân tích...")

                try:
                    # Đảm bảo AI đọc và xử lý văn bản trước khi phản hồi
                    response = self.ai.call_api(user_input)
                    formatted_response = self.ai.format_response(response)

                    # Xóa ký tự ** từ phản hồi của AI
                    formatted_response = self.remove_asterisks(formatted_response)

                    # Xóa tin nhắn "đang phản hồi"
                    try:
                        await typing_message.delete()                    except:
                        pass  # Bỏ qua lỗi nếu không xóa được tin nhắn

                    # Chia tin nhắn nếu quá dài (Telegram giới hạn 4096 ký tự)
                    full_message = f" Zyah King👽: {formatted_response}"
                    if len(full_message) > 4096:
                        # Chia thành nhiều tin nhắn
                        for i in range(0, len(full_message), 4096):
                            chunk = full_message[i:i+4096]
                            chunk = self.remove_asterisks(chunk)  # Đảm bảo xóa ** ở mọi phần
                            await update.message.reply_text(chunk)
                    else:
                        await update.message.reply_text(full_message)

                    self.ai.update_memory(user_input, response)

                except Exception as e:
                    # Nếu có lỗi, vẫn xóa tin nhắn typing và thông báo lỗi
                    try:
                        await typing_message.delete()
                    except:
                        pass
                    error_message = f" Zyah King👽: Đã xảy ra lỗi trong quá trình xử lý"
                    await update.message.reply_text(error_message)

    def run(self):
        try:
            # Khởi động web server để tránh lỗi timeout cổng
            self.start_web_server()

            if TELEGRAM_VERSION == "basic":
                print(f"{Colors.ERROR}[❌] Phiên bản telegram cơ bản không hỗ trợ bot. Vui lòng cài python-telegram-bot{Colors.RESET}")
                return

            # Thêm handlers
            if TELEGRAM_VERSION == "new":
                # Phiên bản mới
                self.app.add_handler(CommandHandler("start", self.start))
                self.app.add_handler(CommandHandler("help", self.help))
                self.app.add_handler(CommandHandler("chatai", self.chatai))
                self.app.add_handler(CommandHandler("thongtinad", self.thongtinad))
                self.app.add_handler(CommandHandler("mua", self.mua))
                self.app.add_handler(CommandHandler("capquyen", self.capquyen))
                self.app.add_handler(CommandHandler("xoaquyen", self.xoaquyen))
                self.app.add_handler(CommandHandler("thongbao", self.thongbao))
                self.app.add_handler(CommandHandler("kiemtra", self.kiemtra))
                self.app.add_handler(CommandHandler("status", self.status))
                self.app.add_handler(CommandHandler("memory", self.memory))
                self.app.add_handler(CommandHandler("backup", self.backup))
                self.app.add_handler(CommandHandler("weather", self.weather))
                self.app.add_handler(CommandHandler("news", self.news))
                self.app.add_handler(CommandHandler("sysinfo", self.sysinfo))

                self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

                print(f"{Colors.INFO}[🌌] Zyah King👽 đang khởi động với tính năng mới...{Colors.RESET}")
                self.log_activity("SYSTEM", "BOT_START")

                self.app.run_polling()

            else:
                # Phiên bản cũ - compatibility mode
                dp = self.app.dispatcher

                dp.add_handler(CommandHandler("start", self.start))
                dp.add_handler(CommandHandler("help", self.help))
                dp.add_handler(CommandHandler("chatai", self.chatai))
                dp.add_handler(CommandHandler("thongtinad", self.thongtinad))
                dp.add_handler(CommandHandler("mua", self.mua))
                dp.add_handler(CommandHandler("capquyen", self.capquyen))
                dp.add_handler(CommandHandler("xoaquyen", self.xoaquyen))
                dp.add_handler(CommandHandler("thongbao", self.thongbao))
                dp.add_handler(CommandHandler("kiemtra", self.kiemtra))
                dp.add_handler(CommandHandler("status", self.status))
                dp.add_handler(CommandHandler("memory", self.memory))
                dp.add_handler(CommandHandler("backup", self.backup))
                dp.add_handler(CommandHandler("weather", self.weather))
                dp.add_handler(CommandHandler("news", self.news))
                dp.add_handler(CommandHandler("sysinfo", self.sysinfo))

                dp.add_handler(MessageHandler(filters.text & ~filters.command, self.handle_message))

                print(f"{Colors.INFO}[🌌] Zyah King👽 đang khởi động (compatibility mode)...{Colors.RESET}")
                self.log_activity("SYSTEM", "BOT_START")

                self.app.start_polling()
                self.app.idle()

        except KeyboardInterrupt:
            self.cleanup()
        except Exception as e:
            print(f"{Colors.ERROR}[💥] Bot crashed: {e}{Colors.RESET}")
            self.cleanup()

    def cleanup(self):
        """Cleanup khi tắt bot"""
        try:
            # Xóa PID file
            if os.path.exists("bot.pid"):
                os.remove("bot.pid")
            print(f"{Colors.INFO}[👋] Zyah King👽 đã tắt an toàn{Colors.RESET}")
            self.log_activity("SYSTEM", "BOT_STOP")
        except:
            pass

# Bot class đã sẵn sàng để import từ bot.py