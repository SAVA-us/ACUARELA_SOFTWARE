import logging
# Ya no importamos FirebaseManager, sino que recibimos el db_handler genérico

logger = logging.getLogger(__name__)

class BarcodeManager:
    """
    Gestiona la lógica de escaneo conectándose al gestor de base de datos (Sheets).
    """
    def __init__(self, db_manager):
        """
        Args:
            db_manager: Instancia de SheetsManager.
        """
        self.db = db_manager

    def handle_inventory_scan(self, barcode: str):
        if not barcode:
            return {'status': 'error', 'message': 'El código de barras no puede estar vacío.'}
        
        try:
            # SheetsManager devuelve un dict simple, perfecto.
            item = self.db.get_inventory_item_details(barcode)
            if item:
                logger.info(f"Producto encontrado: {item['name']}")
                return {'status': 'found', 'item': item}
            else:
                return {'status': 'not_found', 'barcode': barcode}
        except Exception as e:
            logger.error(f"Error escaneo inventario: {e}")
            return {'status': 'error', 'message': str(e)}

    def add_item_to_sale(self, barcode: str, current_sale_items: list):
        if not barcode:
            return current_sale_items, {'status': 'error', 'message': 'Código vacío.'}

        try:
            item_data = self.db.get_inventory_item_details(barcode)
            if not item_data:
                return current_sale_items, {'status': 'error', 'message': f"Producto '{barcode}' no encontrado."}

            # Conversión de tipos segura (Sheets devuelve strings a veces)
            qty_available = int(item_data.get('quantity', 0))
            
            if qty_available <= 0:
                 return current_sale_items, {'status': 'warning', 'message': f"¡Stock agotado para '{item_data['name']}'!"}

            existing_item = next((item for item in current_sale_items if str(item['id']) == str(barcode)), None)
            
            if existing_item:
                if qty_available > existing_item['quantity']:
                    existing_item['quantity'] += 1
                    msg = {'status': 'success', 'message': f"'{item_data['name']}' (+1). Total: {existing_item['quantity']}"}
                else:
                    msg = {'status': 'warning', 'message': f"No hay más stock disponible para '{item_data['name']}'."}
            else:
                new_item = {
                    'id': str(item_data['id']), 
                    'name': item_data['name'],
                    'sale_price': float(item_data.get('sale_price', 0)),
                    'purchase_price': float(item_data.get('purchase_price', 0)),
                    'quantity': 1
                }
                current_sale_items.append(new_item)
                msg = {'status': 'success', 'message': f"'{item_data['name']}' añadido."}
            
            return current_sale_items, msg

        except Exception as e:
            logger.error(f"Error añadiendo a venta: {e}")
            return current_sale_items, {'status': 'error', 'message': str(e)}

    def add_item_to_order_list(self, item_to_add: dict, current_order_items: list, quantity_to_add: int):
        try:
            if not item_to_add:
                 return current_order_items, {'status': 'error', 'message': 'Producto no válido.'}

            qty_available = int(item_to_add.get('quantity', 0))

            if qty_available < quantity_to_add:
                return current_order_items, {'status': 'warning', 'message': f"Stock insuficiente. Disp: {qty_available}"}

            existing_item = next((item for item in current_order_items if str(item['id']) == str(item_to_add['id'])), None)

            if existing_item:
                new_total_quantity = existing_item['order_quantity'] + quantity_to_add
                if qty_available < new_total_quantity:
                    return current_order_items, {'status': 'warning', 'message': f"Tope de stock alcanzado."}
                
                existing_item['order_quantity'] = new_total_quantity
                msg = {'status': 'success', 'message': f"Cantidad actualizada a {new_total_quantity}."}
            else:
                new_order_item = item_to_add.copy()
                new_order_item['order_quantity'] = quantity_to_add
                # Asegurar tipos numéricos
                new_order_item['sale_price'] = float(new_order_item.get('sale_price', 0))
                new_order_item['purchase_price'] = float(new_order_item.get('purchase_price', 0))
                current_order_items.append(new_order_item)
                msg = {'status': 'success', 'message': f"'{item_to_add['name']}' añadido."}
            
            return current_order_items, msg
        except Exception as e:
            logger.error(f"Error en pedido: {e}")
            return current_order_items, {'status': 'error', 'message': str(e)}
