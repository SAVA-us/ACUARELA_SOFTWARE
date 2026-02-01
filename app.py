# -*- coding: utf-8 -*-
"""
HI-DRIVE: Sistema Avanzado de Gestión de Inventario con IA - SAVA SHEETS EDITION
Versión 3.0 - Rapi Tienda Acuarela (Google Sheets Backend)
"""
import streamlit as st
from PIL import Image
import pandas as pd
import plotly.express as px
import json
from datetime import datetime, timedelta, timezone
import numpy as np
import io
import time

# --- Importaciones de utilidades y modelos ---
try:
    # CAMBIO CRÍTICO: Usamos SheetsManager
    from sheets_manager import SheetsManager
    from gemini_utils import GeminiUtils
    from barcode_manager import BarcodeManager
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    from twilio.rest import Client
    IS_TWILIO_AVAILABLE = True
except ImportError as e:
    st.error(f"Error de importación: {e}. Asegúrate de que todas las dependencias estén instaladas.")
    st.stop()


# --- CONFIGURACIÓN DE PÁGINA Y ESTILOS ---
st.set_page_config(
    page_title="Rapi Tienda Acuarela | SAVA Sheets",
    page_icon="https://github.com/GIUSEPPESAN21/LOGO-SAVA/blob/main/LOGO%20COLIBRI.png?raw=true",
    layout="wide"
)

# --- INYECCIÓN DE CSS ---
@st.cache_data
def load_css():
    try:
        with open("style.css") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.warning("Archivo style.css no encontrado. Se usarán estilos por defecto.")

load_css()

# --- INICIALIZACIÓN DE SERVICIOS (CACHED) ---
@st.cache_resource
def initialize_services():
    try:
        # INICIALIZACIÓN DE SHEETS
        db_handler = SheetsManager()
        barcode_handler = BarcodeManager(db_handler) # Inyección de dependencia
        gemini_handler = GeminiUtils()

        twilio_client = None
        # Configuración Twilio
        if IS_TWILIO_AVAILABLE and all(k in st.secrets for k in ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM_NUMBER", "DESTINATION_WHATSAPP_NUMBER"]):
            try:
                twilio_client = Client(st.secrets["TWILIO_ACCOUNT_SID"], st.secrets["TWILIO_AUTH_TOKEN"])
            except Exception as twilio_e:
                st.warning(f"No se pudo inicializar Twilio: {twilio_e}.")
                twilio_client = None 
        else:
             pass

        return db_handler, gemini_handler, twilio_client, barcode_handler
    except Exception as e:
        st.error(f"**Error Crítico de Inicialización:** {e}")
        return None, None, None, None

# Variable 'db' ahora es nuestra instancia de SheetsManager
db, gemini, twilio_client, barcode_manager = initialize_services()

if not all([db, gemini, barcode_manager]):
    st.error("Error al inicializar servicios esenciales. Revisa los secrets.")
    st.stop()

# --- Funciones de Estado de Sesión ---
def init_session_state():
    defaults = {
        'page': "🏠 Inicio", 'order_items': [],
        'editing_item_id': None, 'scanned_item_data': None,
        'usb_scan_result': None, 'usb_sale_items': [],
        'add_sku_input': "", 
        'new_item_name': "", 'new_item_qty': 1, 
        'new_item_purchase': 0.0, 'new_item_sale': 0.0, 'new_item_alert': 0,
        'new_item_supplier': "",
        'should_clear_inventory_form': False
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

# --- DIÁLOGOS DE INTERFAZ ---
@st.dialog("⚠️ Confirmar Eliminación")
def show_delete_confirmation(item_id, item_name):
    st.write(f"¿Estás seguro que deseas eliminar permanentemente el producto **{item_name}** de la hoja de cálculo?")
    
    col1, col2 = st.columns(2)
    if col1.button("🚨 SÍ, ELIMINAR", type="primary", use_container_width=True):
        try:
            with st.spinner("Eliminando fila de Google Sheets..."):
                db.delete_inventory_item(item_id)
            st.success("¡Producto eliminado!")
            st.rerun()
        except Exception as e:
            st.error(f"Error al eliminar: {e}")
            
    if col2.button("Cancelar", use_container_width=True):
        st.rerun()

# --- LÓGICA DE NOTIFICACIONES ---
def send_whatsapp_alert(message):
    if not twilio_client: return
    try:
        from_number = st.secrets["TWILIO_WHATSAPP_FROM_NUMBER"]
        to_number = st.secrets["DESTINATION_WHATSAPP_NUMBER"]
        twilio_client.messages.create(from_=f'whatsapp:{from_number}', body=message, to=f'whatsapp:{to_number}')
        st.toast("¡Alerta enviada!", icon="📲")
    except Exception as e:
        st.error(f"Error Twilio: {e}", icon="🚨")

# --- CALLBACKS ---
def set_clear_form_flag():
    st.session_state.should_clear_inventory_form = True

def save_new_item_callback(supplier_map, current_sku):
    name = st.session_state.get('new_item_name')
    quantity = st.session_state.get('new_item_qty')
    purchase_price = st.session_state.get('new_item_purchase')
    sale_price = st.session_state.get('new_item_sale')
    min_stock_alert = st.session_state.get('new_item_alert')
    selected_supplier_name = st.session_state.get('new_item_supplier')

    if not name:
        st.toast("⚠️ Falta el nombre.", icon="⚠️")
        return

    supplier_id = supplier_map.get(selected_supplier_name, "")

    data = {
        "name": name,
        "quantity": int(quantity),
        "purchase_price": float(purchase_price),
        "sale_price": float(sale_price),
        "min_stock_alert": int(min_stock_alert),
        "supplier_name": selected_supplier_name,
        "supplier_id": supplier_id
    }

    try:
        db.save_inventory_item(data, current_sku, is_new=True)
        st.toast(f"✅ ¡Producto '{name}' guardado en Sheets!", icon="✅")
        st.session_state.should_clear_inventory_form = True
    except Exception as add_e:
        st.toast(f"❌ Error: {add_e}", icon="❌")


# --- NAVEGACIÓN ---
col1, col2, col3 = st.sidebar.columns([1,6,1])
with col2:
    st.image("https://github.com/GIUSEPPESAN21/LOGO-SAVA/blob/main/LOGO%20COLIBRI.png?raw=true", width=150)

st.sidebar.markdown('<h1 style="text-align: center; font-size: 2.0rem; margin-top: -10px;">Rapi Tienda<br>SAVA Sheets</h1>', unsafe_allow_html=True)

PAGES = {
    "🏠 Inicio": "house",
    "🛰️ Escáner USB": "upc-scan",
    "📦 Inventario (Sheets)": "box-seam",
    "🛒 Ventas": "cart4",
    "📊 Analítica": "graph-up-arrow",
    "📥 Descargar Excel": "file-earmark-spreadsheet"
}
for page_name, icon in PAGES.items():
    if st.sidebar.button(f"{page_name}", key=f"nav_{page_name}", width='stretch', type="primary" if st.session_state.page == page_name else "secondary"):
        st.session_state.page = page_name
        st.session_state.editing_item_id = None
        st.session_state.scanned_item_data = None
        st.session_state.usb_scan_result = None
        st.session_state.add_sku_input = ""
        st.session_state.should_clear_inventory_form = False
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.info("Base de Datos: Google Sheets 🟢 Conectado")

# --- RENDERIZADO ---
if st.session_state.page != "🏠 Inicio":
    st.markdown(f'<h1 class="main-header">{st.session_state.page}</h1>', unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)

# --- PÁGINA INICIO ---
if st.session_state.page == "🏠 Inicio":
    st.subheader("Bienvenido a la Versión Google Sheets")
    st.markdown("Todos los datos se guardan en tu hoja de cálculo en tiempo real.")
    
    try:
        items = db.get_all_inventory_items()
        orders = db.get_orders()
        suppliers = db.get_all_suppliers()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("📦 Productos", len(items))
        c2.metric("🧾 Ventas", len(orders))
        c3.metric("👥 Proveedores", len(suppliers))
    except Exception as e:
        st.error(f"Error leyendo Sheets: {e}")

# --- PÁGINA ESCÁNER USB ---
elif st.session_state.page == "🛰️ Escáner USB":
    st.info("Modo compatible con Google Sheets.")
    mode = st.radio("Modo:", ("Inventario", "Venta Rápida"), horizontal=True)
    
    if mode == "Inventario":
        with st.form("inv_scan"):
            code = st.text_input("Código de Barras", key="usb_code")
            if st.form_submit_button("Buscar"):
                res = barcode_manager.handle_inventory_scan(code)
                st.session_state.usb_scan_result = res
                st.rerun()
        
        res = st.session_state.get('usb_scan_result')
        if res and res['status'] == 'found':
            item = res['item']
            st.success(f"Encontrado: {item['name']}")
            with st.form("update_sheet_item"):
                nq = st.number_input("Nueva Cantidad", value=int(item['quantity']))
                np = st.number_input("Nuevo Precio", value=float(item['sale_price']))
                if st.form_submit_button("Actualizar en Sheet"):
                    item['quantity'] = nq
                    item['sale_price'] = np
                    db.save_inventory_item(item, item['id'])
                    st.success("Actualizado en la nube.")
                    st.session_state.usb_scan_result = None
                    
    elif mode == "Venta Rápida":
        code = st.text_input("Escanear para venta", key="sale_code")
        if st.button("Añadir") and code:
            st.session_state.usb_sale_items, msg = barcode_manager.add_item_to_sale(code, st.session_state.usb_sale_items)
            st.toast(msg['message'])
        
        if st.session_state.usb_sale_items:
            # Mostrar tabla simple
            df_preview = pd.DataFrame(st.session_state.usb_sale_items)
            if not df_preview.empty:
                st.dataframe(df_preview[['name', 'quantity', 'sale_price']], use_container_width=True)
                
            total_now = sum(x['sale_price'] * x['quantity'] for x in st.session_state.usb_sale_items)
            st.metric("Total Venta", f"${total_now:,.0f}")
            
            if st.button("Finalizar Venta (Guardar)", type="primary"):
                ok, msg, alerts = db.process_direct_sale(st.session_state.usb_sale_items, "dummy_id")
                if ok:
                    st.success(msg)
                    for a in alerts: st.warning(a)
                    st.session_state.usb_sale_items = []
                else:
                    st.error(f"Error: {msg}")

# --- PÁGINA INVENTARIO ---
elif st.session_state.page == "📦 Inventario (Sheets)":
    tab1, tab2 = st.tabs(["Ver Inventario", "Nuevo Producto"])
    
    with tab1:
        items = db.get_all_inventory_items()
        df = pd.DataFrame(items)
        if not df.empty:
            # Reordenar columnas para mejor lectura si existen
            cols_to_show = ['id', 'name', 'quantity', 'sale_price', 'supplier_name']
            existing_cols = [c for c in cols_to_show if c in df.columns]
            st.dataframe(df[existing_cols], use_container_width=True)
        else:
            st.info("La hoja de inventario está vacía.")
            
    with tab2:
        st.write("Añadir fila a la hoja 'inventory'")
        
        # Bandera de limpieza
        if st.session_state.get('should_clear_inventory_form'):
            st.session_state.add_sku_input = "" 
            st.session_state.new_item_name = ""
            st.session_state.new_item_qty = 1
            st.session_state.new_item_purchase = 0.0
            st.session_state.new_item_sale = 0.0
            st.session_state.new_item_alert = 0
            st.session_state.new_item_supplier = ""
            st.session_state.should_clear_inventory_form = False

        sku_candidate = st.text_input("Código (ID)", key="add_sku_input")
        if sku_candidate:
            existing = db.get_inventory_item_details(sku_candidate)
            if existing:
                st.warning(f"El ID {sku_candidate} ya existe: {existing['name']}")
            else:
                st.success("ID disponible.")
                try:
                    suppliers = db.get_all_suppliers()
                    supplier_map = {s.get('name', 'N/A'): s.get('id', '') for s in suppliers}
                    supplier_names = [""] + list(supplier_map.keys())

                    with st.form("create_item_sheet", clear_on_submit=False):
                        st.text_input("Nombre", key="new_item_name")
                        c1, c2 = st.columns(2)
                        c1.number_input("Cantidad", min_value=1, key="new_item_qty")
                        c2.selectbox("Proveedor", supplier_names, key="new_item_supplier")
                        c3, c4 = st.columns(2)
                        c3.number_input("Costo Compra", key="new_item_purchase")
                        c4.number_input("Precio Venta", key="new_item_sale")
                        st.number_input("Alerta Stock", key="new_item_alert")
                        
                        st.form_submit_button("Guardar en Sheet", type="primary", 
                                            on_click=save_new_item_callback,
                                            args=(supplier_map, sku_candidate))
                except Exception as e:
                    st.error(f"Error cargando proveedores: {e}")

# --- PÁGINA VENTAS ---
elif st.session_state.page == "🛒 Ventas":
    st.subheader("Punto de Venta Completo")
    
    # 1. Selección de items
    items = db.get_all_inventory_items()
    if items:
        item_map = {f"{i['name']} (${i['sale_price']})": i for i in items}
        selected_label = st.selectbox("Buscar Producto", [""] + list(item_map.keys()))
        
        if selected_label:
            item = item_map[selected_label]
            qty = st.number_input("Cantidad", min_value=1, value=1)
            if st.button("Agregar a Orden"):
                st.session_state.order_items, msg = barcode_manager.add_item_to_order_list(item, st.session_state.order_items, qty)
                st.toast(msg['message'])

    # 2. Resumen
    if st.session_state.order_items:
        st.divider()
        st.write("### Resumen de Orden")
        df_order = pd.DataFrame(st.session_state.order_items)
        st.dataframe(df_order[['name', 'order_quantity', 'sale_price']])
        
        total = sum(x['sale_price'] * x['order_quantity'] for x in st.session_state.order_items)
        st.metric("Total a Pagar", f"${total:,.0f}")
        
        col_pay1, col_pay2 = st.columns(2)
        customer = col_pay1.text_input("Cliente", "General")
        method = col_pay2.selectbox("Pago", ["efectivo", "fiado", "transferencia"])
        
        if st.button("Confirmar Venta", type="primary", use_container_width=True):
            order_data = {
                'title': f"Venta {datetime.now().strftime('%H:%M')}",
                'price': total,
                'ingredients': st.session_state.order_items, # barcode manager usa 'ingredients' structure? No, usa lista plana. Adaptamos:
                # El create_order espera una lista de objetos con 'id' y 'quantity'
            }
            # Adaptamos structure para create_order
            # barcode_manager add_item_to_order_list guarda la cantidad en 'order_quantity'
            # pero create_order en sheets_manager espera 'quantity'. Hacemos un mapping rapido
            final_items = []
            for i in st.session_state.order_items:
                i_copy = i.copy()
                i_copy['quantity'] = i['order_quantity']
                final_items.append(i_copy)
            
            order_data['ingredients'] = final_items
            order_data['payment_method'] = method
            order_data['customer_name'] = customer
            
            ok, msg, alerts = db.create_order(order_data)
            if ok:
                st.success("✅ Venta registrada en Google Sheets")
                for a in alerts: st.warning(a)
                st.session_state.order_items = []
                time.sleep(2)
                st.rerun()
            else:
                st.error(f"Error: {msg}")

# --- PÁGINA ANALÍTICA ---
elif st.session_state.page == "📊 Analítica":
    st.title("Reportes en Tiempo Real")
    orders = db.get_orders()
    
    if not orders:
        st.info("No hay ventas registradas.")
    else:
        df = pd.DataFrame(orders)
        # Convertir precios a numerico
        df['price'] = pd.to_numeric(df['price'])
        
        # KPI
        total_ventas = df['price'].sum()
        count_ventas = len(df)
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Ingresos Totales", f"${total_ventas:,.0f}")
        k2.metric("Transacciones", count_ventas)
        if count_ventas > 0:
            k3.metric("Ticket Promedio", f"${total_ventas/count_ventas:,.0f}")
            
        # Grafico
        st.subheader("Ventas Recientes")
        st.line_chart(df.set_index('timestamp_obj')['price'])

# --- PÁGINA EXPORTAR EXCEL ---
elif st.session_state.page == "📥 Descargar Excel":
    st.subheader("Respaldo de Seguridad")
    st.write("Genera una copia física (.xlsx) de tu Google Sheet actual.")
    
    if st.button("Generar Respaldo"):
        with st.spinner("Descargando datos de Google..."):
            inv = db.get_all_inventory_items()
            ord_ = db.get_orders()
            sup = db.get_all_suppliers()
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                pd.DataFrame(inv).to_excel(writer, sheet_name='inventory', index=False)
                pd.DataFrame(ord_).to_excel(writer, sheet_name='orders', index=False)
                pd.DataFrame(sup).to_excel(writer, sheet_name='suppliers', index=False)
            
            output.seek(0)
            st.download_button("⬇️ Descargar", output, "Respaldo_SAVA.xlsx")
