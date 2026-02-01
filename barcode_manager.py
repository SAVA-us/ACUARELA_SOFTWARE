import logging

logger = logging.getLogger(__name__)

class BarcodeManager:
    def __init__(self, db_manager):
        self.db = db_manager

    def handle_inventory_scan(self, barcode: str):
        if not barcode:
            return {'status': 'error', 'message': 'Código vacío.'}
        
        try:
            item = self.db.get_inventory_item_details(barcode)
            if item:
                return {'status': 'found', 'item': item}
            else:
                return {'status': 'not_found', 'barcode': barcode}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def add_item_to_sale(self, barcode: str, current_items: list):
        if not barcode: return current_items, {'status': 'error', 'message': 'Vacío'}

        try:
            item_data = self.db.get_inventory_item_details(barcode)
            if not item_data:
                return current_items, {'status': 'error', 'message': 'No encontrado'}

            # Conversión segura
            try: qty_db = int(item_data.get('quantity', 0))
            except: qty_db = 0
            
            try: price = float(item_data.get('sale_price', 0))
            except: price = 0.0

            if qty_db <= 0:
                 return current_items, {'status': 'warning', 'message': 'Sin Stock'}

            existing = next((i for i in current_items if str(i['id']) == str(item_data['id'])), None)
            
            if existing:
                if qty_db > existing['quantity']:
                    existing['quantity'] += 1
                    msg = {'status': 'success', 'message': '+1 Agregado'}
                else:
                    msg = {'status': 'warning', 'message': 'Tope de stock'}
            else:
                new = {
                    'id': str(item_data['id']),
                    'name': item_data['name'],
                    'sale_price': price,
                    'purchase_price': float(item_data.get('purchase_price', 0) or 0),
                    'quantity': 1
                }
                current_items.append(new)
                msg = {'status': 'success', 'message': 'Agregado'}
            
            return current_items, msg

        except Exception as e:
            return current_items, {'status': 'error', 'message': str(e)}

    def add_item_to_order_list(self, item, current_items, qty_add):
        try:
            qty_db = int(item.get('quantity', 0))
            if qty_db < qty_add:
                return current_items, {'status': 'warning', 'message': 'Stock insuficiente'}

            existing = next((i for i in current_items if str(i['id']) == str(item['id'])), None)

            if existing:
                new_tot = existing['order_quantity'] + qty_add
                if qty_db < new_tot:
                    return current_items, {'status': 'warning', 'message': 'Stock insuficiente'}
                existing['order_quantity'] = new_tot
                msg = {'status': 'success', 'message': 'Actualizado'}
            else:
                new = item.copy()
                new['order_quantity'] = qty_add
                current_items.append(new)
                msg = {'status': 'success', 'message': 'Agregado'}
            return current_items, msg
        except Exception as e:
            return current_items, {'status': 'error', 'message': str(e)}
