import os
from datetime import timedelta
from jinja2 import Environment, FileSystemLoader, select_autoescape
from src.orders.models import Order
from decimal import Decimal

TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "templates",
    "bot"
)

jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape([])
)

def render_start(first_name: str) -> str:
    template = jinja_env.get_template("start.html")
    return template.render(first_name=first_name)

def render_success_invoice(order_id: int, total_amount: Decimal, payment_url: str) -> str:
    template = jinja_env.get_template("success_invoice.html")
    return template.render(order_id=order_id, total_amount=total_amount, payment_url=payment_url)

def render_order_notification(order: Order) -> str:
    template = jinja_env.get_template("order_notification.html")
    date = order.payment_date + timedelta(hours=3) if order.payment_date else None
    date_str = date.strftime("%d.%m.%Y %H:%M") if date else "Не указана"
    return template.render(order=order, date_str=date_str)

def render_payment_invoice() -> str:
    template = jinja_env.get_template("payment_invoice.html")
    return template.render()

def render_pay_button() -> str:
    """Отрендерить текст на кнопке оплаты."""
    template = jinja_env.get_template("pay_button.html")
    return template.render().strip()

def render_order_paid(base_url: str) -> str:
    """Отрендерить сообщение об оплаченном заказе."""
    template = jinja_env.get_template("order_paid.html")
    return template.render(base_url=base_url)
