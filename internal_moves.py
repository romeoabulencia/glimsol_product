####################################################################### 
# 
# # Author: romeo abulencia <romeo.abulencia@gmail.com> 
# Maintainer: romeo abulencia <romeo.abulencia@gmail.com> 
# # This program is free software: you can redistribute it and/or modify 
# it under the terms of the GNU General Public License as published by 
# the Free Software Foundation, either version 3 of the License, or 
# (at your option) any later version. 
# # This program is distributed in the hope that it will be useful, 
# but WITHOUT ANY WARRANTY; without even the implied warranty of 
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the 
# GNU General Public License for more details. 
# # You should have received a copy of the GNU General Public License 
# along with this program. If not, see <http://www.gnu.org/licenses/>. 
#######################################################################
    


from openerp.osv import fields, osv
from openerp import netsvc

class stock_move(osv.osv):
    _inherit="stock.move"
    _name="stock.move"
    
    _columns={
              'parent_id':fields.many2one('stock.move', 'Parent', required=False),
#             'line_number':fields.char('Line number',size=64),

              }
    def create(self, cr, uid, data, context=None):
        result = super(stock_move, self).create(cr, uid, data, context=context)
        #check for product supply method if bundled
        move_obj = self.browse(cr,uid,result)
        product_supply_method = move_obj.product_id.supply_method
        if product_supply_method == 'bundle':
            #loop for product components
            for item in move_obj.product_id.item_ids:
                temp_val = data.copy()
                temp_val['product_id']=item.item_id.id
                temp_val['product_qty']=data['product_qty']*item.qty_uom
                temp_val['parent_id']=result
                self.create(cr,uid,temp_val,context=context)
        return result    
    
    def fetch_all_child(self,cr,uid,parent_id,result=None):
        if not result:
            result = []
        temp_result = self.search(cr,uid,[('parent_id','=',parent_id)])
        result.extend(temp_result)
        for x in temp_result:
            result.extend(self.fetch_all_child(cr, uid, parent_id, result))
        return result
    
#     def write(self, cr, uid, ids, data, context=None):
#         result = super(stock_move, self).write(cr, uid, ids, data, context=context)
#         #if product_id is in data
#         #check for product bundle supply method
#         if not isinstance(ids,list):
#             ids=[ids]
#         for obj in self.browse(cr,uid,ids):
#             product_supply_method = obj.product_id.supply_method
#             #delete all stock move childs
#             #fetch all child
#             target_ids = self.fetch_all_child(cr,uid,obj.id)
#             self.unlink(cr,uid,target_ids)
#             if product_supply_method == 'bundle':
#                 target_fields = ['product_uos_qty', 'date_expected', 'product_uom', 'product_uos', 'prodlot_id', 'product_qty', 'date', 'partner_id', 'product_id', 'name', 'location_id', 'parent_id', 'location_dest_id', 'tracking_id', 'product_packaging', 'type', 'picking_id']
#                 val = self.read(cr,uid,obj.id,target_fields)
#                 for item in obj.product_id.item_ids:
#                     temp_val = val.copy()
#                     temp_val['product_id']=item.item_id.id
#                     temp_val['product_qty']=val['product_qty']*item.qty_uom
#                     temp_val['parent_id']=result
#                     self.create(cr,uid,temp_val,context=context)            
#         return result    
    
    def unlink(self, cr, uid, ids, context=None):
        temp_ids=ids
        if not isinstance(temp_ids,list):
            temp_ids = [temp_ids]
        #remove child ids
        for temp_id in temp_ids:
            child_ids=self.fetch_all_child(cr, uid, temp_id, result)
            self.unlink(cr,uid,child_ids,context=context)
        return super(stock_move, self).unlink(cr, uid, ids, context=context)    
    


class stock_picking(osv.osv):
    _name="stock.picking"
    _inherit="stock.picking"
    
    def onchange_move_lines(self, cr, uid, ids, move_lines,context=None):
        print "onchange_move_lines".upper()
        
        
        return True

class stock_partial_picking(osv.osv_memory):
    _name = "stock.partial.picking"
    _inherit = "stock.partial.picking"
    def default_get(self, cr, uid, fields, context=None):
        if context is None: context = {}
        res = super(stock_partial_picking, self).default_get(cr, uid, fields, context=context)
        picking_ids = context.get('active_ids', [])
        active_model = context.get('active_model')

        if not picking_ids or len(picking_ids) != 1:
            # Partial Picking Processing may only be done for one picking at a time
            return res
        assert active_model in ('stock.picking', 'stock.picking.in', 'stock.picking.out'), 'Bad context propagation'
        picking_id, = picking_ids
        if 'picking_id' in fields:
            res.update(picking_id=picking_id)
        if 'move_ids' in fields:
            picking = self.pool.get('stock.picking').browse(cr, uid, picking_id, context=context)
            moves = [self._partial_move_for(cr, uid, m) for m in picking.move_lines if m.state not in ('done','cancel')]
            #explode bundled product on moves
            res_moves=[]
            for move in moves:
                product_id= move['product_id']
                product_bundle = self.pool.get('purchase.order').get_product_bundle_ids(cr,uid,product_id,context={'product_qty':move['quantity'],'mode':'recursive'})
                if product_bundle:
                    move_data={
                               #'product_id':,
                               #'product_uom':,
                               'prodlot_id':move['prodlot_id'],
                               'location_dest_id':move['location_dest_id'],
                               'location_id':move['location_id'],
                               'move_id':move['move_id'],
                               #'quantity':,
                               }
                    for bundle in product_bundle:
                        temp={'product_id':bundle['item_id'][0],
                              'product_uom':bundle['uom_id'][0],
                              'quantity':bundle['qty_uom'] * move['quantity'],
                              }
                        move_data.update(temp)
                        res_moves.append(move_data.copy())
                else:
                    res_moves.append(move)
                
            res.update(move_ids=res_moves)
        if 'date' in fields:
            res.update
        return res