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