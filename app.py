import streamlit as st
import pandas as pd
import time
from data_manager import DataManager
import gemini_utils

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Rapitienda Acuarela | Enterprise",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Cargar CSS
def local_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

local_css("style.css")

# --- INICIALIZACIÓN DE ESTADO ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = None
if "cart" not in st.session_state:
    st.session_state.cart = []

db = DataManager()

# --- FUNCIONES DE UI ---

def login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style="text-align: center; padding: 2rem;">
            <h1 style="color: #2563eb;">RAPITIENDA ACUARELA</h1>
            <p style="color: #64748b;">Sistema de Gestión Enterprise</p>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("login_form"):
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            submitted = st.form_submit_button("Iniciar Sesión", use_container_width=True)
            
            if submitted:
                user = db.verify_user(username, password)
                if user:
                    st.session_state.logged_in = True
                    st.session_state.user = user
                    st.success("¡Bienvenido!")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos")
        
        st.markdown("""
        <div style="text-align: center; margin-top: 2rem; color: #94a3b8; font-size: 0.8rem;">
            © 2026 Acuarela Software S.A.S
        </div>
        """, unsafe_allow_html=True)

def sidebar_menu():
    with st.sidebar:
        st.markdown("""
        <div style="text-align: center; margin-bottom: 2rem;">
            <div style="font-size: 3rem;">🛍️</div>
            <h3 style="margin:0;">ACUARELA</h3>
            <span style="background: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 12px; font-size: 0.7rem; font-weight: bold;">ENTERPRISE</span>
        </div>
        """, unsafe_allow_html=True)
        
        st.write(f"Hola, **{st.session_state.user['name']}**")
        
        menu = st.radio(
            "Navegación",
            ["Dashboard", "Venta (POS)", "Inventario", "Historial", "Consultor IA"],
            label_visibility="collapsed"
        )
        
        st.markdown("---")
        if st.button("Cerrar Sesión", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user = None
            st.rerun()
            
    return menu

# --- PÁGINAS ---

def dashboard_page():
    st.title("📊 Panel de Control")
    st.markdown("Visión general del negocio en tiempo real.")
    
    metrics = db.get_dashboard_metrics()
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ventas Hoy", f"${metrics['sales_today']:,.0f}")
    c2.metric("Valor Inventario", f"${metrics['inventory_value']:,.0f}")
    c3.metric("Productos Activos", metrics['total_products'])
    c4.metric("Alerta Stock Bajo", metrics['low_stock'], delta_color="inverse")
    
    st.markdown("### 📈 Tendencias Recientes")
    # Gráfico simple de ventas basado en el CSV
    df_sales = db.get_sales_history()
    if not df_sales.empty:
        df_sales['fecha'] = pd.to_datetime(df_sales['timestamp']).dt.date
        daily_sales = df_sales.groupby('fecha')['price'].sum()
        st.line_chart(daily_sales)
    else:
        st.info("No hay datos de ventas suficientes para mostrar gráficos.")

def pos_page():
    st.title("🛒 Punto de Venta")
    
    col_prods, col_cart = st.columns([2, 1])
    
    df_inv = db.get_inventory()
    
    with col_prods:
        st.subheader("Catálogo")
        # Buscador mejorado
        search = st.text_input("🔍 Buscar producto (Nombre o Código)", placeholder="Escanear o escribir...")
        
        filtered_df = df_inv.copy()
        if search:
            # Filtrar por nombre o ID (código de barras)
            mask = filtered_df['name'].astype(str).str.lower().str.contains(search.lower()) | \
                   filtered_df['id'].astype(str).str.contains(search)
            filtered_df = filtered_df[mask]
        
        # Mostrar productos como tarjetas o tabla seleccionable
        if not filtered_df.empty:
            # Usamos un dataframe con selección para añadir rápido
            selection = st.dataframe(
                filtered_df[['id', 'name', 'sale_price', 'quantity']],
                column_config={
                    "sale_price": st.column_config.NumberColumn("Precio", format="$%d"),
                    "quantity": "Stock",
                    "name": "Producto",
                    "id": "Código"
                },
                use_container_width=True,
                selection_mode="single-row",
                on_select="rerun",
                hide_index=True
            )
            
            # Lógica para agregar al carrito al seleccionar
            if selection.selection['rows']:
                selected_idx = selection.selection['rows'][0]
                product = filtered_df.iloc[selected_idx]
                
                # Verificar stock
                in_cart_qty = sum(item['qty'] for item in st.session_state.cart if item['id'] == product['id'])
                if product['quantity'] > in_cart_qty:
                    # Buscar si ya está en carrito
                    found = False
                    for item in st.session_state.cart:
                        if item['id'] == product['id']:
                            item['qty'] += 1
                            found = True
                            break
                    if not found:
                        st.session_state.cart.append({
                            'id': product['id'],
                            'name': product['name'],
                            'sale_price': product['sale_price'],
                            'purchase_price': product.get('purchase_price', 0),
                            'qty': 1
                        })
                    st.toast(f"Agregado: {product['name']}")
                else:
                    st.error("🚫 Stock insuficiente")

        else:
            st.warning("No se encontraron productos.")

    with col_cart:
        st.subheader("Ticket Actual")
        if st.session_state.cart:
            total = 0
            for i, item in enumerate(st.session_state.cart):
                subtotal = item['sale_price'] * item['qty']
                total += subtotal
                
                c1, c2, c3 = st.columns([3, 1, 1])
                with c1:
                    st.write(f"**{item['name']}**")
                    st.caption(f"${item['sale_price']} x {item['qty']}")
                with c2:
                    st.write(f"${subtotal}")
                with c3:
                    if st.button("🗑️", key=f"del_{i}"):
                        st.session_state.cart.pop(i)
                        st.rerun()
                st.divider()
            
            st.markdown(f"### Total: ${total:,.0f}")
            
            payment_method = st.selectbox("Método de Pago", ["Efectivo", "Nequi/Daviplata", "Tarjeta"])
            
            if st.button("✅ Finalizar Venta", type="primary", use_container_width=True):
                if db.register_sale(st.session_state.cart, total, payment_method):
                    st.balloons()
                    st.success("Venta registrada con éxito")
                    st.session_state.cart = []
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("Error al procesar la venta")
        else:
            st.info("El carrito está vacío")
            st.markdown("""
            <div style="text-align: center; font-size: 3rem; opacity: 0.3; margin-top: 2rem;">
                🛒
            </div>
            """, unsafe_allow_html=True)

def inventory_page():
    st.title("📦 Inventario")
    
    tab1, tab2 = st.tabs(["Ver Inventario", "Agregar Producto"])
    
    with tab1:
        df = db.get_inventory()
        # Editor de datos editable
        edited_df = st.data_editor(
            df,
            num_rows="dynamic",
            column_config={
                "sale_price": st.column_config.NumberColumn("Precio Venta", format="$%d"),
                "purchase_price": st.column_config.NumberColumn("Costo", format="$%d"),
                "quantity": st.column_config.NumberColumn("Stock"),
                "name": "Nombre Producto",
                "supplier_name": "Proveedor"
            },
            use_container_width=True,
            key="inventory_editor"
        )
        
        # Botón para guardar cambios masivos
        if st.button("Guardar Cambios en CSV"):
            try:
                edited_df.to_csv(Data_manager.INVENTORY_FILE, index=False)
                st.success("Base de datos de inventario actualizada.")
            except:
                # Fallback simple, idealmente usaríamos el método update del DataManager
                # pero para edición masiva panda directo es más rápido
                edited_df.to_csv('inventory.csv', index=False)
                st.success("Guardado correctamente.")
    
    with tab2:
        with st.form("add_prod_form"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Nombre del Producto")
            code = c2.text_input("Código de Barras / ID")
            
            c3, c4 = st.columns(2)
            price_in = c3.number_input("Precio de Compra", min_value=0)
            price_out = c4.number_input("Precio de Venta", min_value=0)
            
            c5, c6 = st.columns(2)
            qty = c5.number_input("Cantidad Inicial", min_value=0, step=1)
            min_alert = c6.number_input("Alerta Stock Mínimo", min_value=1, value=5)
            
            supplier = st.text_input("Nombre Proveedor")
            
            if st.form_submit_button("Crear Producto"):
                new_prod = {
                    'id': code if code else str(uuid.uuid4())[:8],
                    'name': name,
                    'purchase_price': price_in,
                    'sale_price': price_out,
                    'quantity': qty,
                    'min_stock_alert': min_alert,
                    'supplier_name': supplier,
                    'updated_at': datetime.now().isoformat()
                }
                db.add_product(new_prod)
                st.success("Producto agregado al inventario")

def history_page():
    st.title("📜 Historial de Transacciones")
    df = db.get_sales_history()
    st.dataframe(
        df,
        column_config={
            "price": st.column_config.NumberColumn("Total", format="$%d"),
            "timestamp": "Fecha",
            "status": "Estado"
        },
        use_container_width=True,
        hide_index=True
    )

def ai_page():
    st.title("🤖 Consultor IA")
    st.markdown("Analiza tu inventario y ventas con inteligencia artificial.")
    
    if st.button("Generar Análisis Rápido"):
        with st.spinner("La IA está analizando tus datos..."):
            try:
                # Preparar datos para la IA
                inv = db.get_inventory().to_string()
                sales = db.get_sales_history().tail(20).to_string()
                
                context = f"""
                Actúa como un consultor de negocios experto. Aquí están los datos recientes de mi tienda:
                
                INVENTARIO (Muestra):
                {inv[:1000]}...
                
                VENTAS RECIENTES:
                {sales}
                
                Dame 3 recomendaciones estratégicas para mejorar mis ganancias esta semana.
                Sé breve y directo.
                """
                
                response = gemini_utils.get_gemini_response(context)
                st.markdown("### 💡 Recomendaciones")
                st.write(response)
                
            except Exception as e:
                st.error(f"Error al conectar con IA: {e}")
    
    user_q = st.chat_input("Pregunta algo sobre tu negocio...")
    if user_q:
         with st.chat_message("user"):
             st.write(user_q)
         with st.chat_message("assistant"):
             # Lógica simplificada de chat
             st.write("Analizando...")
             # (Aquí iría la llamada real a Gemini igual que arriba)

# --- ROUTING ---

if not st.session_state.logged_in:
    login_page()
else:
    selection = sidebar_menu()
    
    if selection == "Dashboard":
        dashboard_page()
    elif selection == "Venta (POS)":
        pos_page()
    elif selection == "Inventario":
        inventory_page()
    elif selection == "Historial":
        history_page()
    elif selection == "Consultor IA":
        ai_page()
