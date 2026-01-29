import frappe
from frappe import _
import json

def _require_role():
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Not permitted"), frappe.PermissionError)

def _parse_body():
    data = frappe.request.get_data(as_text=True)
    if not data:
        return {}
    try:
        return frappe.parse_json(data) or {}
    except Exception:
        frappe.throw(_("Invalid JSON body"))

def _upsert_by_filters(doctype: str, filters: dict, data: dict):
    """
    Generic upsert helper.
    - doctype: target doctype name
    - filters: unique lookup filters (dict)
    - data: fields to set/update (dict)
    """
    name = frappe.db.get_value(doctype, filters, "name")
    if name:
        doc = frappe.get_doc(doctype, name)
        doc.update(data)
        doc.save(ignore_permissions=True)
        return {"action": "updated", "name": doc.name}
    else:
        doc = frappe.get_doc({"doctype": doctype, **data})
        doc.insert(ignore_permissions=True)
        return {"action": "created", "name": doc.name}


@frappe.whitelist(methods=["POST"])
def upsert_online_store():
    _require_role()
    payload = _parse_body()

    integration_key = payload.get("integration_key")
    if not integration_key:
        frappe.throw(_("Missing required field: integration_key"))

    # Normalize integration_key
    integration_key = str(integration_key).strip()

    # Extract platform from integration_key (e.g., "SHOPEE:SG:70000101" -> "shopee")
    platform = payload.get("platform")
    if not platform and ":" in integration_key:
        platform = integration_key.split(":")[0].lower()
    if not platform:
        platform = "shopee"  # default fallback

    mapped = {
        # identity
        "integration_key": integration_key,  # unique, used for naming
        "platform": platform,
        "region": payload.get("region"),
        "platform_shop_id": str(payload.get("shop_id")) if payload.get("shop_id") else None,

        # display
        "store_name": payload.get("store_name") or payload.get("shop_name") or f"Store {integration_key}",
        "store_url": payload.get("store_url"),

        # sync tracking
        "last_synced_at": now_datetime(),

        # raw payload
        "raw_payload_json": json.dumps(payload),
    }

    # remove None values so we don't overwrite existing values with null
    mapped = {k: v for k, v in mapped.items() if v is not None}

    # Upsert by integration_key lookup (unique field)
    name = frappe.db.get_value("Online Store", {"integration_key": integration_key}, "name")
    if name:
        doc = frappe.get_doc("Online Store", name)
        doc.update(mapped)
        doc.save(ignore_permissions=True)
        return {"action": "updated", "name": doc.name}
    else:
        doc = frappe.get_doc({"doctype": "Online Store", **mapped})
        doc.insert(ignore_permissions=True)
        return {"action": "created", "name": doc.name}
    
import json
import frappe
from frappe import _
from frappe.utils import get_datetime
from datetime import datetime
from frappe.utils import now_datetime

def _unix_to_dt(ts):
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts))
    except Exception:
        return None

def _safe_json(val, default=None):
    if default is None:
        default = {}
    if val is None:
        return default
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return default
        try:
            return json.loads(s)
        except Exception:
            return default
    return default

def _first_image_url(payload):
    # Your payload has image_json (stringified JSON)
    img = _safe_json(payload.get("image_json"), default={})
    urls = img.get("image_url_list") or []
    return urls[0] if urls else None

def _prices(payload):
    # price_info_json is a list; pick the first entry
    price_list = _safe_json(payload.get("price_info_json"), default=[])
    if isinstance(price_list, list) and price_list:
        p0 = price_list[0] or {}
        return {
            "currency": p0.get("currency") or payload.get("currency"),
            "price_original": p0.get("original_price"),
            "price_final": p0.get("current_price"),
        }
    return {
        "currency": payload.get("currency"),
        "price_original": None,
        "price_final": None,
    }

def _stock_qty(payload):
    # stock_info_v2_json has summary_info.total_available_stock
    stock = _safe_json(payload.get("stock_info_v2_json"), default={})
    summary = stock.get("summary_info") or {}
    total_available = summary.get("total_available_stock")
    if total_available is None:
        return None
    try:
        return int(total_available)
    except Exception:
        return None

def _attrs_to_spec_text(payload):
    # attribute_list_json is list of attributes; turn into readable text
    attrs = _safe_json(payload.get("attribute_list_json"), default=[])
    if not isinstance(attrs, list) or not attrs:
        return None

    lines = []
    for a in attrs:
        name = a.get("original_attribute_name") or a.get("attribute_name") or a.get("attribute_id")
        values = []
        for v in (a.get("attribute_value_list") or []):
            val = v.get("original_value_name") or v.get("value_name") or v.get("value_id")
            unit = v.get("value_unit") or ""
            if val is not None:
                values.append(f"{val}{unit}")
        if name and values:
            lines.append(f"{name}: {', '.join(values)}")

    return "\n".join(lines) if lines else None

def _link_online_store(shop_id, region=None):
    """
    Online Product.store is a Link to Online Store (doctype).
    Build the integration_key using the formula: SHOPEE:{region}:{shop_id}
    and look up by that unique key.
    """
    if not shop_id:
        return None

    if not region:
        return None

    # Build integration_key using the formula
    integration_key = f"SHOPEE:{region}:{shop_id}"
    
    # Look up Online Store by integration_key (unique field)
    name = frappe.db.get_value("Online Store", {"integration_key": integration_key}, "name")
    return name


@frappe.whitelist(methods=["POST"])
def upsert_online_product():
    _require_role()
    payload = _parse_body()

    # Build integration_key from item_id + shop_id + region
    item_id = payload.get("item_id")
    shop_id = payload.get("shop_id")
    region = payload.get("region")

    if not item_id or not shop_id or not region:
        frappe.throw(_("Missing required fields: item_id, shop_id, region"))

    # Normalize and build integration_key
    item_id = str(item_id).strip()
    shop_id = str(shop_id).strip()
    region = str(region).strip()
    integration_key = f"{item_id}-{shop_id}-{region}"

    # Find the Online Store link
    store_link = _link_online_store(shop_id, region)
    if not store_link:
        frappe.throw(_(f"Online Store not found for shop_id={shop_id}, region={region}"))

    # Map item_status to status field (active/inactive/hidden/delisted)
    item_status = payload.get("item_status")
    status = "active"
    if item_status in ("BANNED", "DELETED", "UNLIST"):
        status = "delisted"
    elif item_status in ("REVIEWING",):
        status = "inactive"

    # Get price info
    price_bits = _prices(payload)

    mapped = {
        # identity (required fields)
        "integration_key": integration_key,
        "store": store_link,
        "platform_item_id": str(item_id),
        "product_name": payload.get("item_name"),

        # optional fields
        "status": status,
        "currency": price_bits.get("currency"),
        "current_price": price_bits.get("price_final"),
        "stock_qty": _stock_qty(payload),
        "primary_image_url": _first_image_url(payload),
        "last_synced_at": now_datetime(),
        "raw_payload_json": json.dumps(payload),
    }

    # don't overwrite fields with None
    mapped = {k: v for k, v in mapped.items() if v is not None}

    # Upsert by integration_key (unique field)
    name = frappe.db.get_value("Online Product", {"integration_key": integration_key}, "name")
    if name:
        doc = frappe.get_doc("Online Product", name)
        doc.update(mapped)
        doc.save(ignore_permissions=True)
        return {"action": "updated", "name": doc.name}
    else:
        doc = frappe.get_doc({"doctype": "Online Product", **mapped})
        doc.insert(ignore_permissions=True)
        return {"action": "created", "name": doc.name}

def _safe_json(val, default):
    if val is None:
        return default
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return default
        try:
            return json.loads(s)
        except Exception:
            return default
    return default

def _unix_to_dt(ts):
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts))
    except Exception:
        return None

def _find_online_store(shop_id, region_code):
    if not shop_id or not region_code:
        return None

    # Build integration_key and look up by the unique field
    integration_key = f"SHOPEE:{region_code}:{shop_id}"
    return frappe.db.get_value("Online Store", {"integration_key": integration_key}, "name")


# --------------------------------------------------------------------
# Online Sales Order
# --------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def upsert_online_order():
    _require_role()
    payload = _parse_body()

    # Integration key (order) - expected format: SHOPEE:{region}:{shop_id}:order:{order_id}
    integration_key = payload.get("integration_key")
    if integration_key:
        integration_key = str(integration_key).strip()

    # Resolve region/shop_id for store lookup
    shop_id = payload.get("shop_id")
    region_code = payload.get("region")

    if integration_key:
        parts = integration_key.split(":")
        if not region_code and len(parts) > 1:
            region_code = parts[1]
        if not shop_id and len(parts) > 2:
            shop_id = parts[2]

    # Platform order ID
    platform_order_id = payload.get("order_sn") or payload.get("order_id")
    if not platform_order_id and integration_key:
        parts = integration_key.split(":")
        if len(parts) >= 5 and parts[3] == "order":
            platform_order_id = parts[4]

    if not integration_key:
        if not (region_code and shop_id and platform_order_id):
            frappe.throw(_("Missing required fields: integration_key or region, shop_id, order_id"))
        integration_key = f"SHOPEE:{region_code}:{shop_id}:order:{platform_order_id}"

    if not platform_order_id:
        frappe.throw(_("Missing required field: order_id"))

    store_link = _find_online_store(shop_id, region_code)
    if not store_link:
        frappe.throw(_(f"Online Store not found for shop_id={shop_id}, region={region_code}"))

    # Map order status to allowed values
    status_map = {
        "PENDING": "pending",
        "PROCESSING": "processing",
        "READY_TO_SHIP": "processing",
        "SHIPPED": "shipped",
        "COMPLETED": "completed",
        "CANCELLED": "cancelled",
        "CANCELED": "cancelled",
        "REFUNDED": "refunded",
        "RETURNED": "refunded",
    }
    raw_status = payload.get("order_status")
    status = status_map.get(raw_status) if raw_status else None
    if not status and isinstance(raw_status, str):
        lowered = raw_status.lower()
        if lowered in {"pending", "processing", "shipped", "completed", "cancelled", "refunded"}:
            status = lowered

    mapped = {
        # identity
        "integration_key": integration_key,
        "store": store_link,
        "platform_order_id": str(platform_order_id).strip(),

        # status + money
        "status": status,
        "currency": payload.get("currency"),
        "total_amount": payload.get("total_amount"),

        # dates
        "order_created_at": _unix_to_dt(payload.get("create_time")),
        "last_synced_at": now_datetime(),

        # raw payload
        "raw_payload_json": json.dumps(payload),
    }

    # don't overwrite with None
    mapped = {k: v for k, v in mapped.items() if v is not None}

    # Upsert by integration_key (unique field)
    name = frappe.db.get_value("Online Sales Order", {"integration_key": integration_key}, "name")
    if name:
        doc = frappe.get_doc("Online Sales Order", name)
        doc.update(mapped)
        doc.save(ignore_permissions=True)
        return {"action": "updated", "name": doc.name}
    else:
        doc = frappe.get_doc({"doctype": "Online Sales Order", **mapped})
        doc.insert(ignore_permissions=True)
        return {"action": "created", "name": doc.name}