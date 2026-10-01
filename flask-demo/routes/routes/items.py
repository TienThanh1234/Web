"""Item routes."""
from flask import abort, current_app, redirect, render_template, url_for

from services.auth_service import login_required
from services.item_service import get_item_by_id, load_items


@login_required
def items():
    try:
        item_rows = load_items()

        return render_template(
            "items.html",
            items=item_rows
        )

    except Exception:
        current_app.logger.exception(
            "Không thể tải Items từ Supabase."
        )

        return render_template(
            "items.html",
            items=[],
            load_error=(
                "Không thể tải dữ liệu Items từ Supabase. "
                "Hãy kiểm tra bảng items và RLS policy."
            )
        ), 500


@login_required
def item_detail(item_id):
    item = get_item_by_id(item_id)

    if item is None:
        abort(404)

    return render_template("item_detail.html", item=item)


@login_required
def item():
    return redirect(url_for("items"))


def init_app(app):
    app.add_url_rule("/items", "items", items)
    app.add_url_rule("/items/<item_id>", "item_detail", item_detail)
    app.add_url_rule("/item", "item", item)
