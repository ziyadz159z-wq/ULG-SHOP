import sqlite3
import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks
from discord import app_commands


# ============================================================
#                    إعدادات البوت
# ============================================================

# ضع التوكن الجديد هنا
TOKEN = "MTU0NzUzMDE2NTgyMTc3MTg2Nw.G_3xE9.uUlMkJKzTk1oo11eNGFWprbR9ezKqSxhlUgU5E"

# ID السيرفر
GUILD_ID = 1547261283919859792


# ============================================================
#                         الرومات
# ============================================================

PANEL_CHANNEL_ID = 1547532572614074459
ORDERS_CHANNEL_ID = 1547534211131379712
LOG_CHANNEL_ID = 1547535946482847754


# ============================================================
#                          الرولات
# ============================================================

CUSTOMER_ROLE_ID = 1547263104948244632
SELLER_ROLE_ID = 1547263226603896843
DELETE_ROLE_ID = 1547263006260338930


# ============================================================
#                       إعدادات الوقت
# ============================================================

RED_AFTER_MINUTES = 10
CHECK_INTERVAL = 60


# ============================================================
#                     قاعدة البيانات
# ============================================================

DB_FILE = "orders.db"


# ============================================================
#                         Intents
# ============================================================

intents = discord.Intents.default()


# ============================================================
#                           BOT
# ============================================================

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None
)

db_lock = asyncio.Lock()


# ============================================================
#                           الوقت
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


def iso_now():
    return utc_now().isoformat()


def parse_time(value):
    return datetime.fromisoformat(value)


# ============================================================
#                     قاعدة البيانات
# ============================================================

def connect_db():
    connection = sqlite3.connect(
        DB_FILE,
        timeout=30
    )
    connection.row_factory = sqlite3.Row
    return connection


def init_database():
    connection = connect_db()

    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL DEFAULT 0,
                channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                order_type TEXT NOT NULL,
                quantity TEXT NOT NULL,
                delivery_location TEXT NOT NULL,
                created_at TEXT NOT NULL,
                seller_id INTEGER,
                seller_name TEXT,
                claimed_at TEXT,
                reminded INTEGER NOT NULL DEFAULT 0
            )
            """
        )

        connection.commit()

    finally:
        connection.close()


async def db_execute(
    query,
    params=(),
    fetchone=False,
    fetchall=False,
    commit=False
):
    async with db_lock:
        connection = connect_db()

        try:
            cursor = connection.execute(query, params)

            result = None

            if fetchone:
                result = cursor.fetchone()

            elif fetchall:
                result = cursor.fetchall()

            if commit:
                connection.commit()

            return result

        finally:
            connection.close()


# ============================================================
#                      الصلاحيات
# ============================================================

def has_role(member, role_id):
    if not isinstance(member, discord.Member):
        return False

    return any(
        role.id == role_id
        for role in member.roles
    )


# ============================================================
#                       جلب الروم
# ============================================================

async def get_channel(channel_id):
    channel = bot.get_channel(channel_id)

    if channel is not None:
        return channel

    try:
        return await bot.fetch_channel(channel_id)

    except (
        discord.NotFound,
        discord.Forbidden,
        discord.HTTPException
    ):
        return None


# ============================================================
#                         اللوقات
# ============================================================

async def send_log(
    title,
    description,
    color=None,
    fields=None
):
    if color is None:
        color = discord.Color.blurple()

    channel = await get_channel(LOG_CHANNEL_ID)

    if channel is None:
        return

    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=utc_now()
    )

    if fields:
        for name, value, inline in fields:
            embed.add_field(
                name=name,
                value=value,
                inline=inline
            )

    embed.set_footer(
        text="ULG SHOP • نظام الطلبات الاحترافي"
    )

    try:
        await channel.send(embed=embed)

    except (
        discord.Forbidden,
        discord.HTTPException
    ):
        pass


# ============================================================
#                           DM
# ============================================================

async def send_dm(user_id, embed):
    try:
        user = bot.get_user(user_id)

        if user is None:
            user = await bot.fetch_user(user_id)

        await user.send(embed=embed)

        return True

    except (
        discord.NotFound,
        discord.Forbidden,
        discord.HTTPException
    ):
        return False


# ============================================================
#                     Embed الطلب
# ============================================================

def create_order_embed(
    order,
    red=False,
    claimed=False
):
    if claimed:
        color = discord.Color.green()
        status = "🟢 تم استلام الطلب"

        description = (
            f"تم استلام طلبك من قبل "
            f"**{order['seller_name']}**.\n\n"
            "⏳ يتم الآن تجهيز طلبك."
        )

    else:
        if red:
            color = discord.Color.red()
            status = "🔴 الطلب متأخر"

            description = (
                "⚠️ هذا الطلب لم يتم استلامه "
                "حتى الآن."
            )

        else:
            color = discord.Color.blurple()
            status = "🔵 بانتظار الاستلام"

            description = (
                "هذا الطلب بانتظار أحد البائعين."
            )

    embed = discord.Embed(
        title=f"📦 طلب رقم #{order['id']}",
        description=description,
        color=color,
        timestamp=parse_time(order["created_at"])
    )

    embed.add_field(
        name="👤 العميل",
        value=str(order["username"]),
        inline=True
    )

    embed.add_field(
        name="📝 نوع الطلب",
        value=str(order["order_type"]),
        inline=True
    )

    embed.add_field(
        name="🔢 الكمية",
        value=str(order["quantity"]),
        inline=True
    )

    embed.add_field(
        name="📍 مكان التوصيل",
        value=str(order["delivery_location"]),
        inline=False
    )

    embed.add_field(
        name="📊 الحالة",
        value=status,
        inline=True
    )

    if claimed:
        embed.add_field(
            name="🧑‍💼 البائع",
            value=str(order["seller_name"]),
            inline=True
        )

    embed.set_footer(
        text="ULG SHOP • نظام الطلبات الاحترافي"
    )

    return embed


# ============================================================
#                     مودال الطلب
# ============================================================

class OrderModal(
    discord.ui.Modal,
    title="إضافة طلب جديد"
):

    customer_name = discord.ui.TextInput(
        label="اسمك في الخادم؟",
        placeholder="اكتب اسمك في الخادم",
        required=True,
        max_length=100
    )

    quantity = discord.ui.TextInput(
        label="ما هي الكمية؟",
        placeholder="مثال: 1 / 5 / 10",
        required=True,
        max_length=100
    )

    delivery_location = discord.ui.TextInput(
        label="مكان التوصيل",
        placeholder="اكتب مكان التوصيل",
        required=True,
        max_length=300
    )

    def __init__(self, order_type):
        super().__init__()
        self.order_type = order_type

    async def on_submit(self, interaction):

        if not isinstance(
            interaction.user,
            discord.Member
        ):
            await interaction.response.send_message(
                "❌ تعذر التحقق من صلاحياتك.",
                ephemeral=True
            )
            return

        if interaction.guild_id != GUILD_ID:
            await interaction.response.send_message(
                "❌ هذا السيرفر غير مهيأ للبوت.",
                ephemeral=True
            )
            return

        if not has_role(
            interaction.user,
            CUSTOMER_ROLE_ID
        ):
            await interaction.response.send_message(
                "❌ ليس لديك صلاحية إضافة طلب.",
                ephemeral=True
            )
            return

        channel = await get_channel(
            ORDERS_CHANNEL_ID
        )

        if channel is None:
            await interaction.response.send_message(
                "❌ روم الطلبات غير موجود.",
                ephemeral=True
            )
            return

        created_at = iso_now()

        async with db_lock:
            connection = connect_db()

            try:
                cursor = connection.execute(
                    """
                    INSERT INTO orders (
                        guild_id,
                        message_id,
                        channel_id,
                        user_id,
                        username,
                        order_type,
                        quantity,
                        delivery_location,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        interaction.guild_id,
                        0,
                        ORDERS_CHANNEL_ID,
                        interaction.user.id,
                        self.customer_name.value.strip(),
                        self.order_type,
                        self.quantity.value.strip(),
                        self.delivery_location.value.strip(),
                        created_at
                    )
                )

                order_id = cursor.lastrowid

                connection.commit()

            finally:
                connection.close()

        order = await db_execute(
            "SELECT * FROM orders WHERE id = ?",
            (order_id,),
            fetchone=True
        )

        if order is None:
            await interaction.response.send_message(
                "❌ حدث خطأ أثناء إنشاء الطلب.",
                ephemeral=True
            )
            return

        embed = create_order_embed(order)

        try:
            message = await channel.send(
                embed=embed,
                view=OrderView(order_id)
            )

        except (
            discord.Forbidden,
            discord.HTTPException
        ):
            await db_execute(
                "DELETE FROM orders WHERE id = ?",
                (order_id,),
                commit=True
            )

            await interaction.response.send_message(
                "❌ تعذر إرسال الطلب.",
                ephemeral=True
            )
            return

        await db_execute(
            """
            UPDATE orders
            SET message_id = ?
            WHERE id = ?
            """,
            (
                message.id,
                order_id
            ),
            commit=True
        )

        confirmation = discord.Embed(
            title="✅ تم إرسال طلبك",
            description=(
                f"تم إنشاء طلبك **#{order_id}** بنجاح.\n\n"
                "سيتم إشعارك في الخاص عند استلام الطلب."
            ),
            color=discord.Color.green()
        )

        confirmation.set_footer(
            text="ULG SHOP • نظام الطلبات الاحترافي"
        )

        await interaction.response.send_message(
            embed=confirmation,
            ephemeral=True
        )

        await send_log(
            "🆕 طلب جديد",
            f"تم إنشاء الطلب **#{order_id}**.",
            discord.Color.blurple(),
            [
                (
                    "العميل",
                    interaction.user.mention,
                    True
                ),
                (
                    "النوع",
                    self.order_type,
                    True
                ),
                (
                    "الكمية",
                    self.quantity.value,
                    True
                ),
                (
                    "مكان التوصيل",
                    self.delivery_location.value,
                    False
                )
            ]
        )


# ============================================================
#                 اختيار نوع الطلب
# ============================================================

class OrderTypeSelect(
    discord.ui.Select
):

    def __init__(self):

        # خيارات قانونية
        options = [

            discord.SelectOption(
                label="طلب منتج",
                value="طلب منتج",
                emoji="📦"
            ),

            discord.SelectOption(
                label="طلب مستحقات التلفيل",
                value="طلب مستحقات التلفيل",
                emoji="💰"
            ),

            discord.SelectOption(
                label="طلب خدمة",
                value="طلب خدمة",
                emoji="🛠️"
            ),

            discord.SelectOption(
                label="طلب خاص",
                value="طلب خاص",
                emoji="⭐"
            )

        ]

        super().__init__(
            placeholder="اختر نوع الطلب",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction):

        if not isinstance(
            interaction.user,
            discord.Member
        ):
            await interaction.response.send_message(
                "❌ تعذر التحقق من الصلاحية.",
                ephemeral=True
            )
            return

        if not has_role(
            interaction.user,
            CUSTOMER_ROLE_ID
        ):
            await interaction.response.send_message(
                "❌ ليس لديك صلاحية.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            OrderModal(
                self.values[0]
            )
        )


class OrderTypeView(
    discord.ui.View
):

    def __init__(self):
        super().__init__(
            timeout=120
        )

        self.add_item(
            OrderTypeSelect()
        )


# ============================================================
#                     زر إضافة طلب
# ============================================================

class AddOrderButton(
    discord.ui.Button
):

    def __init__(self):

        super().__init__(
            label="إضافة طلب",
            emoji="✅",
            style=discord.ButtonStyle.success,
            custom_id="orders:add"
        )

    async def callback(self, interaction):

        if not isinstance(
            interaction.user,
            discord.Member
        ):
            await interaction.response.send_message(
                "❌ تعذر التحقق من الصلاحية.",
                ephemeral=True
            )
            return

        if not has_role(
            interaction.user,
            CUSTOMER_ROLE_ID
        ):
            await interaction.response.send_message(
                "❌ هذا الزر مخصص لأصحاب الصلاحية فقط.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🛍️ ULG SHOP",

            description=(
                "## مرحبًا بكم في ULG SHOP 🛍️\n\n"

                "لإضافة طلب جديد، يمكنكم الضغط على زر "
                "**إضافة طلب** الموجود بالأسفل.\n\n"

                "⚠️ **يرجى احترام قوانين المتجر وعدم "
                "مخالفتها، لتجنب التعرض للعقوبة.**\n\n"

                "نتمنى لكم تجربة ممتازة معنا 🤍"
            ),

            color=discord.Color.blurple()
        )

        embed.set_footer(
            text="ULG SHOP • نظام الطلبات الاحترافي"
        )

        await interaction.response.send_message(
            embed=embed,
            view=OrderTypeView(),
            ephemeral=True
        )


class ControlPanelView(
    discord.ui.View
):

    def __init__(self):
        super().__init__(
            timeout=None
        )

        self.add_item(
            AddOrderButton()
        )


# ============================================================
#                    استلام الطلب
# ============================================================

class ClaimOrderButton(
    discord.ui.Button
):

    def __init__(
        self,
        order_id,
        red=False
    ):

        super().__init__(
            label="استلام الطلب",
            emoji="📥",

            style=(
                discord.ButtonStyle.danger
                if red
                else discord.ButtonStyle.primary
            ),

            custom_id=f"orders:claim:{order_id}"
        )

        self.order_id = order_id

    async def callback(self, interaction):

        if not isinstance(
            interaction.user,
            discord.Member
        ):
            await interaction.response.send_message(
                "❌ تعذر التحقق من الصلاحية.",
                ephemeral=True
            )
            return

        if not has_role(
            interaction.user,
            SELLER_ROLE_ID
        ):
            await interaction.response.send_message(
                "❌ هذا الزر مخصص للبائعين فقط.",
                ephemeral=True
            )
            return

        claimed_at = iso_now()

        async with db_lock:
            connection = connect_db()

            try:
                cursor = connection.execute(
                    """
                    UPDATE orders
                    SET
                        seller_id = ?,
                        seller_name = ?,
                        claimed_at = ?
                    WHERE
                        id = ?
                        AND seller_id IS NULL
                    """,
                    (
                        interaction.user.id,
                        interaction.user.display_name,
                        claimed_at,
                        self.order_id
                    )
                )

                connection.commit()

                success = cursor.rowcount == 1

            finally:
                connection.close()

        if not success:
            await interaction.response.send_message(
                "⚠️ تم استلام الطلب من بائع آخر بالفعل.",
                ephemeral=True
            )
            return

        order = await db_execute(
            "SELECT * FROM orders WHERE id = ?",
            (self.order_id,),
            fetchone=True
        )

        if order is None:
            await interaction.response.send_message(
                "❌ تعذر العثور على الطلب.",
                ephemeral=True
            )
            return

        channel = await get_channel(
            order["channel_id"]
        )

        if channel:

            try:
                message = await channel.fetch_message(
                    order["message_id"]
                )

                await message.edit(
                    embed=create_order_embed(
                        order,
                        claimed=True
                    ),
                    view=ClaimedOrderView(
                        self.order_id
                    )
                )

            except (
                discord.NotFound,
                discord.Forbidden,
                discord.HTTPException
            ):
                pass

        dm_embed = discord.Embed(
            title="📦 تم استلام طلبك",

            description=(
                f"تم استلام طلبك **#{self.order_id}** بنجاح.\n\n"
                f"🧑‍💼 البائع: "
                f"**{interaction.user.display_name}**\n\n"
                "⏳ يتم الآن تجهيز طلبك."
            ),

            color=discord.Color.green()
        )

        dm_embed.set_footer(
            text="ULG SHOP • نظام الطلبات الاحترافي"
        )

        dm_sent = await send_dm(
            order["user_id"],
            dm_embed
        )

        await send_log(
            "📥 استلام طلب",

            f"تم استلام الطلب **#{self.order_id}**.",

            discord.Color.green(),

            [
                (
                    "البائع",
                    interaction.user.mention,
                    True
                ),

                (
                    "العميل",
                    f"<@{order['user_id']}>",
                    True
                ),

                (
                    "الخاص",
                    "تم الإرسال"
                    if dm_sent
                    else "تعذر الإرسال",
                    True
                )
            ]
        )

        await interaction.response.send_message(
            "✅ تم استلام الطلب بنجاح.",
            ephemeral=True
        )


# ============================================================
#                         التذكير
# ============================================================

class RemindButton(
    discord.ui.Button
):

    def __init__(self, order_id):

        super().__init__(
            label="تذكير",
            emoji="🔔",
            style=discord.ButtonStyle.secondary,
            custom_id=f"orders:remind:{order_id}"
        )

        self.order_id = order_id

    async def callback(self, interaction):

        if not isinstance(
            interaction.user,
            discord.Member
        ):
            await interaction.response.send_message(
                "❌ تعذر التحقق من الصلاحية.",
                ephemeral=True
            )
            return

        if not has_role(
            interaction.user,
            SELLER_ROLE_ID
        ):
            await interaction.response.send_message(
                "❌ زر التذكير مخصص للبائعين فقط.",
                ephemeral=True
            )
            return

        order = await db_execute(
            "SELECT * FROM orders WHERE id = ?",
            (self.order_id,),
            fetchone=True
        )

        if order is None:
            await interaction.response.send_message(
                "❌ الطلب غير موجود.",
                ephemeral=True
            )
            return

        if order["seller_id"] != interaction.user.id:
            await interaction.response.send_message(
                "❌ التذكير متاح للبائع الذي استلم الطلب فقط.",
                ephemeral=True
            )
            return

        dm_embed = discord.Embed(
            title="🔔 طلبك جاهز",

            description=(
                f"<@{order['user_id']}>\n\n"
                f"طلبك **#{self.order_id}** أصبح جاهزًا للاستلام.\n\n"
                "📦 يرجى التوجه لاستلام طلبك."
            ),

            color=discord.Color.gold()
        )

        dm_embed.set_footer(
            text="ULG SHOP • نظام الطلبات الاحترافي"
        )

        sent = await send_dm(
            order["user_id"],
            dm_embed
        )

        if sent:

            await db_execute(
                """
                UPDATE orders
                SET reminded = 1
                WHERE id = ?
                """,
                (self.order_id,),
                commit=True
            )

            await interaction.response.send_message(
                "🔔 تم إرسال التذكير للعميل.",
                ephemeral=True
            )

        else:

            await interaction.response.send_message(
                "⚠️ تعذر إرسال الرسالة الخاصة للعميل.",
                ephemeral=True
            )

        await send_log(
            "🔔 تذكير",

            f"تم تنفيذ تذكير للطلب **#{self.order_id}**.",

            discord.Color.gold(),

            [
                (
                    "البائع",
                    interaction.user.mention,
                    True
                ),
                (
                    "العميل",
                    f"<@{order['user_id']}>",
                    True
                )
            ]
        )


# ============================================================
#                       حذف الطلب
# ============================================================

class DeleteOrderButton(
    discord.ui.Button
):

    def __init__(self, order_id):

        super().__init__(
            label="حذف الطلب",
            emoji="🗑️",
            style=discord.ButtonStyle.danger,
            custom_id=f"orders:delete:{order_id}"
        )

        self.order_id = order_id

    async def callback(self, interaction):

        if not isinstance(
            interaction.user,
            discord.Member
        ):
            await interaction.response.send_message(
                "❌ تعذر التحقق من الصلاحية.",
                ephemeral=True
            )
            return

        if not has_role(
            interaction.user,
            DELETE_ROLE_ID
        ):
            await interaction.response.send_message(
                "❌ ليس لديك صلاحية حذف الطلب.",
                ephemeral=True
            )
            return

        order = await db_execute(
            "SELECT * FROM orders WHERE id = ?",
            (self.order_id,),
            fetchone=True
        )

        if order is None:
            await interaction.response.send_message(
                "⚠️ الطلب غير موجود.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            DeleteReasonModal(
                self.order_id,
                order
            )
        )


# ============================================================
#                    مودال سبب الحذف
# ============================================================

class DeleteReasonModal(
    discord.ui.Modal,
    title="حذف الطلب"
):

    reason = discord.ui.TextInput(
        label="سبب حذف الطلب",
        placeholder="اكتب سبب حذف الطلب",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    def __init__(
        self,
        order_id,
        order
    ):
        super().__init__()

        self.order_id = order_id
        self.order = order

    async def on_submit(self, interaction):

        if not isinstance(
            interaction.user,
            discord.Member
        ):
            await interaction.response.send_message(
                "❌ تعذر التحقق من الصلاحية.",
                ephemeral=True
            )
            return

        if not has_role(
            interaction.user,
            DELETE_ROLE_ID
        ):
            await interaction.response.send_message(
                "❌ ليس لديك صلاحية حذف الطلب.",
                ephemeral=True
            )
            return

        reason = self.reason.value.strip()

        await db_execute(
            "DELETE FROM orders WHERE id = ?",
            (self.order_id,),
            commit=True
        )

        try:
            channel = await get_channel(
                self.order["channel_id"]
            )

            if channel:

                message = await channel.fetch_message(
                    self.order["message_id"]
                )

                await message.delete()

        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException
        ):
            pass

        dm_embed = discord.Embed(
            title="🗑️ تم حذف طلبك",

            description=(
                f"تم حذف طلبك **#{self.order_id}**."
            ),

            color=discord.Color.red()
        )

        dm_embed.add_field(
            name="📌 سبب الحذف",
            value=reason,
            inline=False
        )

        dm_embed.set_footer(
            text="ULG SHOP • نظام الطلبات الاحترافي"
        )

        dm_sent = await send_dm(
            self.order["user_id"],
            dm_embed
        )

        await send_log(
            "🗑️ حذف طلب",

            f"تم حذف الطلب **#{self.order_id}**.",

            discord.Color.red(),

            [
                (
                    "المسؤول",
                    interaction.user.mention,
                    True
                ),
                (
                    "العميل",
                    f"<@{self.order['user_id']}>",
                    True
                ),
                (
                    "السبب",
                    reason,
                    False
                ),
                (
                    "إرسال الخاص",
                    "تم" if dm_sent else "تعذر الإرسال",
                    True
                )
            ]
        )

        await interaction.response.send_message(
            f"✅ تم حذف الطلب **#{self.order_id}**.",
            ephemeral=True
        )


# ============================================================
#                  View الطلب قبل الاستلام
# ============================================================

class OrderView(
    discord.ui.View
):

    def __init__(
        self,
        order_id,
        red=False
    ):
        super().__init__(
            timeout=None
        )

        self.add_item(
            ClaimOrderButton(
                order_id,
                red
            )
        )

        self.add_item(
            DeleteOrderButton(
                order_id
            )
        )


# ============================================================
#                  View الطلب بعد الاستلام
# ============================================================

class ClaimedOrderView(
    discord.ui.View
):

    def __init__(self, order_id):

        super().__init__(
            timeout=None
        )

        status_button = discord.ui.Button(
            label="تم استلام الطلب",
            emoji="✅",
            style=discord.ButtonStyle.success,
            disabled=True,
            custom_id=f"orders:status:{order_id}"
        )

        self.add_item(status_button)

        self.add_item(
            RemindButton(order_id)
        )

        self.add_item(
            DeleteOrderButton(order_id)
        )


# ============================================================
#                مراقبة الطلبات كل دقيقة
# ============================================================

@tasks.loop(
    seconds=CHECK_INTERVAL,
    reconnect=True
)
async def update_order_colors():

    orders = await db_execute(
        """
        SELECT *
        FROM orders
        WHERE seller_id IS NULL
        AND message_id != 0
        """,
        fetchall=True
    )

    current_time = utc_now()

    for order in orders:

        try:
            created = parse_time(
                order["created_at"]
            )

            elapsed_minutes = (
                current_time - created
            ).total_seconds() / 60

            red = (
                elapsed_minutes
                >= RED_AFTER_MINUTES
            )

            channel = await get_channel(
                order["channel_id"]
            )

            if channel is None:
                continue

            message = await channel.fetch_message(
                order["message_id"]
            )

            await message.edit(
                embed=create_order_embed(
                    order,
                    red=red,
                    claimed=False
                ),
                view=OrderView(
                    order["id"],
                    red
                )
            )

        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException
        ):
            continue

        except Exception as error:
            print(
                f"❌ Order update error: {error}"
            )


@update_order_colors.before_loop
async def before_update_order_colors():
    await bot.wait_until_ready()


@update_order_colors.error
async def update_order_colors_error(error):
    print(
        f"❌ Background task error: {error}"
    )


# ============================================================
#                  إنشاء لوحة التحكم
# ============================================================

async def create_control_panel():

    channel = await get_channel(
        PANEL_CHANNEL_ID
    )

    if channel is None:

        print(
            "❌ لم يتم العثور على روم لوحة التحكم."
        )

        return None

    embed = discord.Embed(

        title="🛍️ ULG SHOP",

        description=(
            "## مرحبًا بكم في ULG SHOP 🛍️\n\n"

            "لإضافة طلب جديد، يمكنكم الضغط على زر "
            "**إضافة طلب** الموجود بالأسفل.\n\n"

            "⚠️ **يرجى احترام قوانين المتجر وعدم "
            "مخالفتها، لتجنب التعرض للعقوبة.**\n\n"

            "نتمنى لكم تجربة ممتازة معنا 🤍"
        ),

        color=discord.Color.blurple()
    )

    embed.set_footer(
        text="ULG SHOP • نظام الطلبات الاحترافي"
    )

    try:

        message = await channel.send(
            embed=embed,
            view=ControlPanelView()
        )

        return message

    except (
        discord.Forbidden,
        discord.HTTPException
    ) as error:

        print(
            f"❌ Panel send error: {error}"
        )

        return None


# ============================================================
#                       Slash /setup
# ============================================================

@bot.tree.command(
    name="setup",
    description="إنشاء لوحة تحكم الطلبات"
)
@app_commands.default_permissions(
    administrator=True
)
async def setup_command(interaction):

    if not isinstance(
        interaction.user,
        discord.Member
    ):
        return

    if interaction.guild_id != GUILD_ID:

        await interaction.response.send_message(
            "❌ هذا السيرفر غير مهيأ للبوت.",
            ephemeral=True
        )

        return

    if not interaction.user.guild_permissions.administrator:

        await interaction.response.send_message(
            "❌ تحتاج صلاحية Administrator.",
            ephemeral=True
        )

        return

    await interaction.response.defer(
        ephemeral=True
    )

    message = await create_control_panel()

    if message is None:

        await interaction.followup.send(
            "❌ تعذر إنشاء لوحة التحكم.",
            ephemeral=True
        )

        return

    await send_log(
        "🎛️ لوحة التحكم",

        f"تم إنشاء لوحة التحكم بواسطة "
        f"{interaction.user.mention}.",

        discord.Color.blurple()
    )

    await interaction.followup.send(
        "✅ تم إنشاء لوحة التحكم.",
        ephemeral=True
    )


# ============================================================
#                      أمر !setup
# ============================================================

@bot.command(
    name="setup"
)
@commands.has_permissions(
    administrator=True
)
async def setup_prefix(ctx):

    if ctx.guild is None:
        return

    if ctx.guild.id != GUILD_ID:
        return

    message = await create_control_panel()

    if message is None:
        await ctx.send(
            "❌ تعذر إنشاء لوحة التحكم."
        )
        return

    await ctx.send(
        "✅ تم إنشاء لوحة التحكم."
    )


@setup_prefix.error
async def setup_error(ctx, error):

    if isinstance(
        error,
        commands.MissingPermissions
    ):
        await ctx.send(
            "❌ تحتاج صلاحية Administrator."
        )


# ============================================================
#                         on_ready
# ============================================================

@bot.event
async def on_ready():

    print()
    print("==========================================")
    print("             ULG SHOP BOT")
    print("==========================================")
    print(f"Bot       : {bot.user}")
    print(f"Bot ID    : {bot.user.id}")
    print(f"Guild ID  : {GUILD_ID}")
    print("Database  : orders.db")
    print("Status    : ONLINE")
    print("==========================================")
    print()


# ============================================================
#                       setup_hook
# ============================================================

@bot.event
async def setup_hook():

    print(
        "🔧 Initializing database..."
    )

    init_database()

    print(
        "✅ Database ready."
    )

    bot.add_view(
        ControlPanelView()
    )

    print(
        "✅ Control panel view loaded."
    )

    orders = await db_execute(
        "SELECT * FROM orders",
        fetchall=True
    )

    restored = 0

    for order in orders:

        try:

            if order["seller_id"] is None:

                bot.add_view(
                    OrderView(
                        order["id"]
                    )
                )

            else:

                bot.add_view(
                    ClaimedOrderView(
                        order["id"]
                    )
                )

            restored += 1

        except Exception as error:

            print(
                f"❌ View restore error "
                f"for #{order['id']}: {error}"
            )

    print(
        f"✅ Restored views: {restored}"
    )

    guild = discord.Object(
        id=GUILD_ID
    )

    bot.tree.copy_global_to(
        guild=guild
    )

    try:

        synced = await bot.tree.sync(
            guild=guild
        )

        print(
            f"✅ Slash commands synced: "
            f"{len(synced)}"
        )

    except Exception as error:

        print(
            f"❌ Slash sync error: {error}"
        )

    if not update_order_colors.is_running():

        update_order_colors.start()

        print(
            "✅ Order monitoring started."
        )


# ============================================================
#                  التحقق من التوكن
# ============================================================

def validate_config():

    if not TOKEN:

        print(
            "❌ لم يتم وضع توكن البوت."
        )

        return False

    if TOKEN == "ضع_توكن_البوت_الجديد_هنا":

        print(
            "❌ ضع توكن البوت الحقيقي داخل TOKEN."
        )

        return False

    if not GUILD_ID:

        print(
            "❌ GUILD_ID غير موجود."
        )

        return False

    return True


# ============================================================
#                         START
# ============================================================

def main():

    print()
    print(
        "🚀 Starting ULG SHOP bot..."
    )

    print(
        "🔄 Discord reconnect: ENABLED"
    )

    print(
        "🟢 Process mode: ENABLED"
    )

    print()

    if not validate_config():
        return

    try:

        bot.run(
            TOKEN,
            reconnect=True
        )

    except discord.LoginFailure:

        print()
        print(
            "❌ التوكن غير صحيح."
        )
        print(
            "اعمل Reset Token من Discord Developer Portal."
        )
        print()

    except KeyboardInterrupt:

        print()
        print(
            "🛑 تم إيقاف البوت يدويًا."
        )
        print()

    except Exception as error:

        print()
        print(
            f"❌ حدث خطأ: {error}"
        )
        print()


# ============================================================
#                         تشغيل
# ============================================================

if __name__ == "__main__":
    main()