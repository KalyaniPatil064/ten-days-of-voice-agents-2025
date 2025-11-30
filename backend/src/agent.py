import json
import logging
import os
import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Annotated

from dotenv import load_dotenv
from pydantic import Field
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RoomInputOptions,
    WorkerOptions,
    cli,
    function_tool,
    RunContext,
)

from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

# -------------------------
# Logging
# -------------------------
logger = logging.getLogger("vastura_ethnic_agent")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(handler)

load_dotenv(".env.local")

# ======================================================
# ------------------- VASTURA ETHNIC CATALOG -------------------
# ======================================================
# Focused on Kurtis, Sarees, and Dupattas (Indian Ethnic Wear)

CATALOG = [
    # --- KURTIS ---
    {
        "id": "kurti-001",
        "name": "Elegant Cotton Chikankari Kurti",
        "description": "Premium cotton kurti with delicate white Chikankari embroidery, perfect for casual wear.",
        "price": 1800,
        "currency": "INR",
        "category": "kurti",
        "color": "White",
        "detail": "Chikankari",
        "sizes": ["S", "M", "L", "XL"],
    },
    {
        "id": "kurti-002",
        "name": "Festive Silk Blend Kurti",
        "description": "Silk blend straight kurti ideal for festivals and evening events, featuring light Zari work.",
        "price": 3500,
        "currency": "INR",
        "category": "kurti",
        "color": "Maroon",
        "detail": "Zari Work",
        "sizes": ["M", "L", "XL"],
    },
    # --- SAREES ---
    {
        "id": "saree-001",
        "name": "Traditional Chiffon Saree",
        "description": "Lightweight chiffon saree with a simple gold border, easy to drape.",
        "price": 4500,
        "currency": "INR",
        "category": "saree",
        "color": "Navy",
        "detail": "Plain Border",
        "sizes": ["Free"], # Sarees typically 'Free Size'
    },
    {
        "id": "saree-002",
        "name": "Banarasi Art Silk Saree",
        "description": "Heavy art silk saree with traditional brocade weaving, suitable for weddings.",
        "price": 8900,
        "currency": "INR",
        "category": "saree",
        "color": "Red",
        "detail": "Brocade",
        "sizes": ["Free"],
    },
    # --- DUPATTAS ---
    {
        "id": "dup-001",
        "name": "Solid Georgette Dupatta",
        "description": "Simple, solid color dupatta, essential for matching any kurti.",
        "price": 600,
        "currency": "INR",
        "category": "dupatta",
        "color": "Yellow",
        "detail": "Solid",
        "sizes": ["Free"],
    },
    # --- CONTRAST ITEM (for flexible searching) ---
    {
        "id": "access-001",
        "name": "Kundan Style Earrings",
        "description": "Heavy Kundan stone earrings, perfect accessory for festive wear.",
        "price": 1500,
        "currency": "INR",
        "category": "jewelry",
        "color": "Gold",
        "detail": "Kundan",
        "sizes": [],
    },
]


ORDERS_FILE = "orders.json"

if not os.path.exists(ORDERS_FILE):
    with open(ORDERS_FILE, "w") as f:
        json.dump([], f)

# -------------------------
# Per-session Userdata (shopping-centric)
# -------------------------
@dataclass
class Userdata:
    customer_name: Optional[str] = None
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    cart: List[Dict] = field(default_factory=list)
    orders: List[Dict] = field(default_factory=list)
    history: List[Dict] = field(default_factory=list)

# -------------------------
# Merchant-layer helpers 
# -------------------------

def _load_all_orders() -> List[Dict]:
    try:
        with open(ORDERS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save_order(order: Dict):
    orders = _load_all_orders()
    orders.append(order)
    with open(ORDERS_FILE, "w") as f:
        json.dump(orders, f, indent=2)


def list_products(filters: Optional[Dict] = None) -> List[Dict]:
    """Naive filtering by category, max_price, color, size substring, or query words."""
    filters = filters or {}
    results = []
    query = filters.get("q")
    category = filters.get("category")
    max_price = filters.get("max_price") or filters.get("to") or filters.get("max")
    min_price = filters.get("min_price") or filters.get("from") or filters.get("min")
    color = filters.get("color")
    size = filters.get("size")

    # normalize category synonyms
    if category:
        cat = category.lower()
        if cat in ("kurti", "kurtis", "tunic"):
            category = "kurti"
        elif cat in ("saree", "saris"):
            category = "saree"
        elif cat in ("dupatta", "scarf"):
            category = "dupatta"
        else:
            category = cat

    for p in CATALOG:
        ok = True
        # category matching
        if category:
            pcat = p.get("category", "").lower()
            if pcat != category and category not in pcat and pcat not in category:
                ok = False
        if max_price:
            try:
                if p.get("price", 0) > int(max_price):
                    ok = False
            except Exception:
                pass
        if min_price:
            try:
                if p.get("price", 0) < int(min_price):
                    ok = False
            except Exception:
                pass
        if color and p.get("color") and p.get("color").lower() != color.lower():
            ok = False
        if size and (p.get('category') in ['kurti'] and (not p.get("sizes") or size.upper() not in p.get("sizes"))):
            ok = False
        if query:
            q = query.lower()
            if q not in p.get("name", "").lower() and q not in p.get("description", "").lower():
                ok = False

        if ok:
            results.append(p)
    return results


def find_product_by_ref(ref_text: str, candidates: Optional[List[Dict]] = None) -> Optional[Dict]:
    """Resolve references like 'second kurti' or 'navy saree' to a product dict."""
    ref = (ref_text or "").lower().strip()
    cand = candidates if candidates is not None else CATALOG

    # ordinal handling (1st, 2nd, etc.)
    ordinals = {"first": 0, "second": 1, "third": 2, "fourth": 3}
    for word, idx in ordinals.items():
        if word in ref:
            if idx < len(cand):
                return cand[idx]

    # direct id match
    for p in cand:
        if p["id"].lower() == ref:
            return p

    # color + category matching (e.g., 'navy saree')
    for p in cand:
        if p.get("color") and p["color"].lower() in ref and p.get("category") and p["category"] in ref:
            return p

    # name substring or keywords
    for p in cand:
        name = p["name"].lower()
        if all(tok in name for tok in ref.split() if len(tok) > 2):
            return p
            
    # numeric index like '2' -> second
    for token in ref.split():
        if token.isdigit():
            idx = int(token) - 1
            if 0 <= idx < len(cand):
                return cand[idx]

    return None


def create_order_object(line_items: List[Dict], currency: str = "INR") -> Dict:
    """line_items: [{product_id, quantity, attrs}]
    Returns an order dict (id, items, total, currency, created_at)
    """
    items = []
    total = 0
    for li in line_items:
        pid = li.get("product_id")
        qty = int(li.get("quantity", 1))
        prod = next((p for p in CATALOG if p["id"] == pid), None)
        if not prod:
            raise ValueError(f"Product {pid} not found")
        line_total = prod["price"] * qty
        total += line_total
        items.append({
            "product_id": pid,
            "name": prod["name"],
            "unit_price": prod["price"],
            "quantity": qty,
            "line_total": line_total,
            "attrs": li.get("attrs", {}),
        })
    order = {
        "id": f"order-{str(uuid.uuid4())[:8]}",
        "items": items,
        "total": total,
        "currency": currency,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    # persist
    _save_order(order)
    return order


def get_most_recent_order() -> Optional[Dict]:
    all_orders = _load_all_orders()
    if not all_orders:
        return None
    return all_orders[-1]

# -------------------------
# Agent Tools (function_tool) exposed to the LLM layer
# -------------------------

@function_tool
async def show_catalog(
    ctx: RunContext[Userdata],
    q: Annotated[Optional[str], Field(description="Search query (optional)", default=None)] = None,
    category: Annotated[Optional[str], Field(description="Category (optional)", default=None)] = None,
    max_price: Annotated[Optional[int], Field(description="Maximum price (optional)", default=None)] = None,
    color: Annotated[Optional[str], Field(description="Color (optional)", default=None)] = None,
) -> str:
    """Return a short spoken summary of matching products (name, price, id)."""
    userdata = ctx.userdata
    filters = {"q": q, "category": category, "max_price": max_price, "color": color}
    prods = list_products({k: v for k, v in filters.items() if v is not None})
    
    if not prods:
        return "Sorry — I couldn't find any ethnic wear or accessories that match. Would you like to try another search?"
    
    # Summarize top 4 ethnic items and hint at required attributes
    lines = [f"Here are the top {min(4, len(prods))} items I found at Vastura:"]
    
    product_data_for_frontend = [] 
    
    for idx, p in enumerate(prods[:4], start=1):
        size_info = f" (sizes: {', '.join(p['sizes'])})" if p.get('sizes') and p.get('category') == 'kurti' else ""
        lines.append(f"{idx}. {p['name']} ({p.get('detail')}) — {p['price']} {p['currency']} (id: {p['id']}){size_info}")
        
        # Prepare data for the frontend to visually display images
        # Use a combination of category and detail/color for unique image mapping
        image_key = f"{p['category']}_{p.get('detail', p.get('color'))}".replace(" ", "_").lower()
        
        product_data_for_frontend.append({
            "id": p["id"],
            "name": p["name"],
            "price": p["price"],
            "image_key": image_key, 
            "category": p["category"],
            "color": p["color"],
            "sizes": p.get('sizes')
        })

    lines.append("To buy an item, please tell me the item ID, quantity, and size (if needed for kurtis).")
    
    # Returning structured JSON for the frontend to visually update the page.
    return json.dumps({
        "spoken_summary": "\n".join(lines),
        "product_data": product_data_for_frontend
    })


@function_tool
async def add_to_cart(
    ctx: RunContext[Userdata],
    product_ref: Annotated[str, Field(description="Reference to product: id, name, or spoken ref")] ,
    quantity: Annotated[int, Field(description="Quantity", default=1)] = 1,
    size: Annotated[Optional[str], Field(description="Size (S, M, L, XL, or 'Free') (optional)", default=None)] = None,
) -> str:
    """Resolve a product and add to the session cart. Validates size for kurtis."""
    userdata = ctx.userdata
    candidates = CATALOG
    prod = find_product_by_ref(product_ref, candidates)
    
    if not prod:
        return "I couldn't resolve which product you meant. Try using the item id or say 'show catalog' to hear options.'"

    # Size validation logic for Kurtis (requires size)
    if prod.get("category") == 'kurti':
        if not size or size.upper() not in prod["sizes"]:
            # If size is required but not provided or invalid, ask for it
            return f"Please specify the size for the {prod['name']}. Available sizes are: {', '.join(prod['sizes'])}."
        size = size.upper() # Standardize size

    # For Sarees/Dupattas, size is 'Free'
    elif prod.get("category") in ['saree', 'dupatta']:
        size = 'Free'
    else:
        size = None # Accessories/Other items

    # Update/Add to cart
    line_items_key = (prod["id"], size)
    
    # Check if item with same ID/size is already in the cart
    found = False
    for li in userdata.cart:
        current_size = li.get("attrs", {}).get("size")
        if li["product_id"] == prod["id"] and current_size == size:
            li["quantity"] = li.get("quantity", 0) + quantity
            found = True
            break
            
    if not found:
        # Add new item to cart
        userdata.cart.append({
            "product_id": prod["id"],
            "quantity": int(quantity),
            "attrs": {"size": size} if size else {},
        })
        
    userdata.history.append({
        "time": datetime.utcnow().isoformat() + "Z",
        "action": "add_to_cart",
        "product_id": prod["id"],
        "quantity": int(quantity),
    })
    
    sz_text = f" in size {size}" if size else ""
    return f"Added {quantity} x {prod['name']}{sz_text} to your cart. What would you like to do next?"


@function_tool
async def show_cart(
    ctx: RunContext[Userdata],
) -> str:
    userdata = ctx.userdata
    if not userdata.cart:
        return "Your cart is empty. You can say 'show catalog' to browse items.'"
    
    lines = ["Items in your cart:"]
    total = 0
    for li in userdata.cart:
        p = next((x for x in CATALOG if x["id"] == li["product_id"]), None)
        if not p:
            continue
        line_total = p["price"] * li.get("quantity", 1)
        total += line_total
        sz = li.get("attrs", {}).get("size")
        sz_text = f", size {sz}" if sz else ""
        lines.append(f"- {p['name']} x {li['quantity']}{sz_text}: {line_total} INR")
    
    lines.append(f"Cart total: {total} INR")
    lines.append("Say 'place my order' to checkout or 'clear cart' to empty the cart.")
    return "\n".join(lines)


@function_tool
async def clear_cart(
    ctx: RunContext[Userdata],
) -> str:
    userdata = ctx.userdata
    userdata.cart = []
    userdata.history.append({"time": datetime.utcnow().isoformat() + "Z", "action": "clear_cart"})
    return "Your cart has been cleared. What would you like to do next?"


@function_tool
async def place_order(
    ctx: RunContext[Userdata],
    confirm: Annotated[bool, Field(description="Confirm order placement", default=True)] = True,
) -> str:
    """Create order from session cart and persist. Returns order summary."""
    userdata = ctx.userdata
    if not userdata.cart:
        return "Your cart is empty — nothing to place. Would you like to browse items?"
    
    line_items = []
    for li in userdata.cart:
        line_items.append({
            "product_id": li["product_id"],
            "quantity": li.get("quantity", 1),
            "attrs": li.get("attrs", {}),
        })
        
    order = create_order_object(line_items)
    userdata.orders.append(order)
    userdata.history.append({"time": datetime.utcnow().isoformat() + "Z", "action": "place_order", "order_id": order["id"]})
    
    # clear cart after order
    userdata.cart = []
    return f"Order placed. Order ID {order['id']}. Total {order['total']} {order['currency']}. Thank you for shopping with Vastura! What would you like to do next?"


@function_tool
async def last_order(
    ctx: RunContext[Userdata],
) -> str:
    ord = get_most_recent_order()
    if not ord:
        return "You have no past orders yet."
    lines = [f"Most recent order: {ord['id']} — {ord['created_at']}"]
    for it in ord['items']:
        lines.append(f"- {it['name']} x {it['quantity']}: {it['line_total']} {ord['currency']}")
    lines.append(f"Total: {ord['total']} {ord['currency']}")
    return "\n".join(lines)

# -------------------------
# The Agent (VasturaAgent)
# -------------------------
class VasturaAgent(Agent):
    def __init__(self):
        instructions = """
        You are 'Elara', the friendly shopping assistant for Vastura Ethnic Wear.
        Universe: A high-quality online boutique specializing in Indian ethnic garments (Kurtis, Sarees, Dupattas).
        Tone: Warm, elegant, and professional; keep sentences short for voice clarity.
        Role: Help the customer browse the catalog, add items to cart, place orders, and review recent orders.

        Rules:
            - When adding Kurtis, you MUST ensure the size is specified (S, M, L, XL). If the size is missing, ask for it immediately. Sarees and Dupattas are Free Size.
            - When presenting options from the catalog, mention the garment type (e.g., Kurti, Saree), the price, and the ID.
            - Items are referred to by their ID (e.g., 'kurti-001').
        """
        super().__init__(
            instructions=instructions,
            tools=[show_catalog, add_to_cart, show_cart, clear_cart, place_order, last_order],
        )

# -------------------------
# Entrypoint & Prewarm
# -------------------------
def prewarm(proc: JobProcess):
    try:
        proc.userdata["vad"] = silero.VAD.load()
    except Exception:
        logger.warning("VAD prewarm failed; continuing without preloaded VAD.")


async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    logger.info("\n" + "🛍️" * 6)
    logger.info("🚀 STARTING VASTURA ETHNIC WEAR AGENT — Elara")

    userdata = Userdata()

    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=google.LLM(model="gemini-2.5-flash"),
        tts=murf.TTS(
            voice="en-US-alicia", 
            style="Conversational",
            text_pacing=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata.get("vad"),
        userdata=userdata,
    )

    await session.start(
        agent=VasturaAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(noise_cancellation=noise_cancellation.BVC()),
    )

    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
