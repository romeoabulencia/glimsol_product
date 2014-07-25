    
    


from openerp.osv import fields, osv

#Delivery Order
#Incoming Shipments
class stock_move(osv.osv):
    _name="stock.move"
    _inherit="stock.move"
    
    def _check_prod_lot_id(self, cr, uid, ids): 

        for dict in self.read(cr,uid,ids,['prodlot_id','type']):
            print "dict".upper(),dict
            if dict['prodlot_id'] and self.search(cr,uid,[('prodlot_id','=',dict['prodlot_id'][0]),('type','=',dict['type']),('id','!=',dict['id'])]):
                return False
        return True
    _constraints = [(_check_prod_lot_id, 'Error: Serial number already been used!', ['prodlot_id']), ]    
    

class stock_production_lot(osv.osv):
    _name='stock.production.lot'
    _inherit="stock.production.lot"
    def _get_availability(self, cr, uid, ids, name, arg, context=None):
        res={}
        for dict_ in self.read(cr,uid,ids,['move_ids']):
            res[dict_['id']]='on_stock'
            cr.execute("select sp.id from stock_move sm \
                                    inner join stock_production_lot spl on (spl.id = sm.prodlot_id) \
                                    inner join stock_picking sp on (sm.picking_id = sp.id) where sp.type='out' and spl.id = %s" % dict_['id'])
            if cr.fetchone():
                res[dict_['id']]='out_of_stock'
        return res    
    _columns={
        'availability': fields.function(_get_availability, type='selection', string='Availability', store=False,
            selection= [
                  ('on_stock','On Stock'),
                  ('out_of_stock','Out of Stock'),
                   ]),              
              }
    

    
    _defaults = {  
        'availability': 'on_stock',  
        }
    
    def _check_name(self, cr, uid, ids): 
        for dict in self.read(cr,uid,ids,['name']):
            if self.search(cr,uid,[('name','=',dict['name']),('id','!=',dict['id'])]):
                return False
        return True
    _constraints = [(_check_name, 'Error: Serial number already been used!', ['name']), ] 
    
    
#Physical Inventories
class stock_inventory_line(osv.osv):
    _inherit="stock.inventory.line"
    _name="stock.inventory.line"
    
    def _check_prod_lot_id(self, cr, uid, ids): 

        for dict in self.read(cr,uid,ids,['prod_lot_id']):
            if dict['prod_lot_id'] and self.search(cr,uid,[('prod_lot_id','=',dict['prod_lot_id'][0]),('id','!=',dict['id'])]):
                return False
        return True
    _constraints = [(_check_prod_lot_id, 'Error: Serial number already been used!', ['prod_lot_id']), ]     