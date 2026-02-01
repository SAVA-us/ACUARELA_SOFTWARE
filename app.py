# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import io
import time
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(
    page_title="Rapi Tienda | SAVA Sheets",
    page_icon="https://github.com/GIUSEPPESAN21/LOGO-SAVA/blob/main/LOGO%20COLIBRI.png?raw=true",
    layout="wide"
)

# --- CARGA SERVICIOS ---
try:
    from sheets_manager import SheetsManager
    from gemini_utils import GeminiUtils
    from barcode_manager import BarcodeManager
    from twilio.rest import Client
except ImportError:
    st.error("Error cargando librerías. Revisa requirements.txt")
    st.stop()

@st.cache_resource
def load_db():
    try:
        return SheetsManager()
    except Exception as e:
        return None

db = load_db()

if not db:
    st.error("❌ Error conectando a Google Sheets. Verifica los Secrets y que la hoja exista.")
    st.info("El sistema intentará crear las hojas automáticamente si la conexión es correcta.")
    st.stop()

barcode_manager = BarcodeManager(db)
gemini = GeminiUtils()

# --- ESTADO ---
if 'page' not in st.session_state: st.session_state.page = "🏠 Inicio"
if 'usb_sale_items' not in st.session_state: st.session_state.usb_sale_items = []
if 'order_items' not in st.session_state: st.session_state.order_items = []

# --- CSS ---
st.markdown("""
<style>
    .stButton>button {width: 100%; border-radius: 8px;}
    .metric-card {background: #f0f2f6; padding: 15px; border-radius: 10px;}
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://github.com/GIUSEPPESAN21/LOGO-SAVA/blob/main/LOGO%20COLIBRI.png?raw=true", width=120)
    st.title("SAVA Sheets")
    
    pages = ["🏠 Inicio", "🛰️ Escáner USB", "📦 Inventario", "🛒 Ventas", "📊 Analítica", "📥 Descargar Excel"]
    
    for p in pages:
        if st.button(p, type="primary" if st.session_state.page == p else "secondary"):
            st.session_state.page = p
            st.rerun()

# --- PÁGINAS ---

if st.session_state.page == "🏠 Inicio":
    st.header("Panel de Control")
    try:
        n_inv = len(db.get_all_inventory_items())
        n_ord = db.get_order_count()
        
        c1, c2 = st.columns(2)
        c1.metric("Productos en Inventario", n_inv)
        c2.metric("Ventas Totales", n_ord)
    except Exception as e:
        st.error(f"Error leyendo datos: {e}")

elif st.session_state.page == "🛰️ Escáner USB":
    st.header("Escáner Rápido")
    mode = st.radio("Modo", ["Inventario", "Venta"], horizontal=True)
    
    code = st.text_input("Código de Barras", key="scan_input")
    
    if mode == "Inventario":
        if code:
            res = barcode_manager.handle_inventory_scan(code)
            if res['status'] == 'found':
                item = res['item']
                st.success(f"📦 {item['name']}")
                st.write(f"Stock: {item['quantity']} | Precio: ${item['sale_price']}")
                
                with st.form("edit_fast"):
                    nq = st.number_input("Nuevo Stock", value=int(item['quantity']))
                    np = st.number_input("Nuevo Precio", value=float(item['sale_price']))
                    if st.form_submit_button("Actualizar"):
                        item['quantity'] = nq
                        item['sale_price'] = np
                        db.save_inventory_item(item, item['id'])
                        st.success("Guardado")
                        time.sleep(1)
                        st.rerun()
            elif res['status'] == 'not_found':
                st.warning("Producto no encontrado. Ve a Inventario para crearlo.")
    
    else: # Venta
        if code:
            st.session_state.usb_sale_items, msg = barcode_manager.add_item_to_sale(code, st.session_state.usb_sale_items)
            st.toast(msg['message'])
        
        if st.session_state.usb_sale_items:
            df = pd.DataFrame(st.session_state.usb_sale_items)
            st.dataframe(df[['name', 'quantity', 'sale_price', 'subtotal' if 'subtotal' in df else 'sale_price']], use_container_width=True)
            
            total = sum(x['sale_price'] * x['quantity'] for x in st.session_state.usb_sale_items)
            st.metric("Total", f"${total:,.0f}")
            
            if st.button("Cobrar", type="primary"):
                ok, msg, _ = db.process_direct_sale(st.session_state.usb_sale_items, "dummy")
                if ok:
                    st.success(msg)
                    st.session_state.usb_sale_items = []
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(msg)

elif st.session_state.page == "📦 Inventario":
    st.header("Gestión de Inventario")
    tab1, tab2 = st.tabs(["Lista", "Crear Nuevo"])
    
    with tab1:
        items = db.get_all_inventory_items()
        if items:
            df = pd.DataFrame(items)
            # Mostrar solo columnas relevantes si existen
            cols = ['id', 'name', 'quantity', 'sale_price', 'supplier_name']
            show_cols = [c for c in cols if c in df.columns]
            st.dataframe(df[show_cols], use_container_width=True)
    
    with tab2:
        with st.form("new_prod"):
            nid = st.text_input("Código de Barras (ID)")
            nname = st.text_input("Nombre")
            c1, c2 = st.columns(2)
            nqty = c1.number_input("Cantidad", min_value=1)
            nprice = c2.number_input("Precio Venta", min_value=0.0)
            npurch = c1.number_input("Costo Compra", min_value=0.0)
            nsupp = c2.text_input("Proveedor")
            
            if st.form_submit_button("Guardar"):
                if nid and nname:
                    data = {
                        "name": nname, "quantity": nqty,
                        "sale_price": nprice, "purchase_price": npurch,
                        "supplier_name": nsupp
                    }
                    db.save_inventory_item(data, nid, is_new=True)
                    st.success("Creado")
                else:
                    st.error("Faltan datos")

elif st.session_state.page == "🛒 Ventas":
    st.header("Punto de Venta")
    items = db.get_all_inventory_items()
    
    if items:
        # Buscador
        names = [f"{i['name']} | ${i['sale_price']}" for i in items]
        sel = st.selectbox("Buscar producto", [""] + names)
        
        if sel:
            # Encontrar item original
            target_name = sel.split(" | ")[0]
            item = next((i for i in items if i['name'] == target_name), None)
            
            qty = st.number_input("Cantidad", 1, 100, 1)
            if st.button("Agregar"):
                st.session_state.order_items, msg = barcode_manager.add_item_to_order_list(item, st.session_state.order_items, qty)
                st.toast(msg['message'])
    
    if st.session_state.order_items:
        st.divider()
        df = pd.DataFrame(st.session_state.order_items)
        st.dataframe(df[['name', 'order_quantity', 'sale_price']])
        
        total = sum(x['sale_price'] * x['order_quantity'] for x in st.session_state.order_items)
        st.metric("Total a Pagar", f"${total:,.0f}")
        
        c1, c2 = st.columns(2)
        cli = c1.text_input("Cliente", "General")
        pay = c2.selectbox("Método", ["efectivo", "fiado", "transferencia"])
        
        if st.button("Finalizar Venta", type="primary"):
            # Adaptar estructura para create_order
            final_items = []
            for i in st.session_state.order_items:
                x = i.copy()
                x['quantity'] = i['order_quantity']
                final_items.append(x)
            
            data = {
                'title': f"Venta {datetime.now().strftime('%H:%M')}",
                'price': total,
                'ingredients': final_items,
                'payment_method': pay,
                'customer_name': cli
            }
            
            ok, msg, alerts = db.create_order(data)
            if ok:
                st.success("Venta Exitosa")
                if alerts: st.warning("\n".join(alerts))
                st.session_state.order_items = []
                time.sleep(2)
                st.rerun()
            else:
                st.error(msg)

elif st.session_state.page == "📊 Analítica":
    st.header("Reportes")
    orders = db.get_orders()
    if orders:
        df = pd.DataFrame(orders)
        try:
            df['price'] = pd.to_numeric(df['price'])
            st.bar_chart(df, x='timestamp', y='price')
            st.metric("Total Vendido Histórico", f"${df['price'].sum():,.0f}")
        except:
            st.dataframe(df)
    else:
        st.info("Sin datos aún")

elif st.session_state.page == "📥 Descargar Excel":
    st.header("Backup")
    if st.button("Generar Excel"):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            pd.DataFrame(db.get_all_inventory_items()).to_excel(writer, sheet_name='inventory', index=False)
            pd.DataFrame(db.get_orders()).to_excel(writer, sheet_name='orders', index=False)
            pd.DataFrame(db.get_all_suppliers()).to_excel(writer, sheet_name='suppliers', index=False)
        output.seek(0)
        st.download_button("Descargar .xlsx", output, "SAVA_Backup.xlsx")
