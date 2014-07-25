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


class purchase_order(osv.osv):    
    _name="purchase.order"
    _inherit="purchase.order"
    def get_product_bundle_ids(self,cr,uid,product_id,context=None):
        #fetch connected product item entries
        product_qty=context['product_qty']

        cr.execute('select id from product_item where product_id = %s' % product_id)
        product_item_ids = [x[0] for x in cr.fetchall()]
        target_product_item_fields = ['item_id','qty_uom','uom_id']
        res = self.pool.get('product.item').read(cr,uid,product_item_ids,target_product_item_fields)
        #multiply product qty
        for x in res:
            x['qty_uom']=x['qty_uom']*product_qty
        if context and 'mode' in context and context['mode'] == 'recursive':
            for temp_product_id in res:
                context.update({'product_qty':temp_product_id['qty_uom']})
                temp_res = self.get_product_bundle_ids(cr, uid, temp_product_id['item_id'][0], context)
                #remove bundled product from list
                if temp_res:
                    res.remove(temp_product_id)
                res.extend(temp_res)
        return res
    
    def _prepare_order_line_move(self, cr, uid, order, order_line, picking_id, context=None):
        
        res =  {
            'name': order_line.name or '',
            'product_id': order_line.product_id.id,
            'product_qty': order_line.product_qty,
            'product_uos_qty': order_line.product_qty,
            'product_uom': order_line.product_uom.id,
            'product_uos': order_line.product_uom.id,
            'date': self.date_to_datetime(cr, uid, order.date_order, context),
            'date_expected': self.date_to_datetime(cr, uid, order_line.date_planned, context),
            'location_id': order.partner_id.property_stock_supplier.id,
            'location_dest_id': order.location_id.id,
            'picking_id': picking_id,
            'partner_id': order.dest_address_id.id or order.partner_id.id,
            'move_dest_id': order_line.move_dest_id.id,
            'state': 'draft',
            'type':'in',
            'purchase_line_id': order_line.id,
            'company_id': order.company_id.id,
            'price_unit': order_line.price_unit
        }    
        if context and 'product_bundle in context':
            #prep data to be used on creating stock moves for bundles
            parent = context['order']
            fin_res=[]
  
            
            for pb_item in context['product_bundle']:
                product_id = pb_item['item_id'][0]
                date_planned=order_line.date_planned
                name=pb_item['item_id'][1]
                price_unit=order_line.price_unit
                ol_qty=order_line.product_qty
                  
                product_onchange_res=self.pool.get('purchase.order.line').onchange_product_id(cr,uid,0,parent.pricelist_id.id,product_id,pb_item['qty_uom'],pb_item['uom_id'][0],parent.partner_id.id, parent.date_order,parent.fiscal_position.id,date_planned,name,price_unit,context)['value']
                temp_res={'name':product_onchange_res['name'],
                          'product_id':pb_item['item_id'][0],
                          'product_qty':product_onchange_res['product_qty'],
                          'product_uos_qty':product_onchange_res['product_qty'],
                          'product_uom':product_onchange_res['product_uom'],
                          'product_uos':product_onchange_res['product_uom'],
                          'price_unit':product_onchange_res['price_unit']                          
                          }
                res.update(temp_res)
                fin_res.append(res.copy())
            return fin_res
              
            
        return res
    
    def _create_pickings(self, cr, uid, order, order_lines, picking_id=False, context=None):
        """Creates pickings and appropriate stock moves for given order lines, then
        confirms the moves, makes them available, and confirms the picking.

        If ``picking_id`` is provided, the stock moves will be added to it, otherwise
        a standard outgoing picking will be created to wrap the stock moves, as returned
        by :meth:`~._prepare_order_picking`.

        Modules that wish to customize the procurements or partition the stock moves over
        multiple stock pickings may override this method and call ``super()`` with
        different subsets of ``order_lines`` and/or preset ``picking_id`` values.

        :param browse_record order: purchase order to which the order lines belong
        :param list(browse_record) order_lines: purchase order line records for which picking
                                                and moves should be created.
        :param int picking_id: optional ID of a stock picking to which the created stock moves
                               will be added. A new picking will be created if omitted.
        :return: list of IDs of pickings used/created for the given order lines (usually just one)
        """
        if not picking_id:
            picking_id = self.pool.get('stock.picking').create(cr, uid, self._prepare_order_picking(cr, uid, order, context=context))
        todo_moves = []
        stock_move = self.pool.get('stock.move')
        wf_service = netsvc.LocalService("workflow")
        for order_line in order_lines:

            if not order_line.product_id:
                continue
            if order_line.product_id.type in ('product', 'consu'):
            
                #check for bundled product
                if order_line.product_id.supply_method == 'bundle':
                    product_bundle = self.get_product_bundle_ids(cr, uid, order_line.product_id.id, {'mode':'recursive','product_qty':order_line.product_qty})

                    
                    stock_move_create_data = self._prepare_order_line_move(cr, uid, order, order_line, picking_id, context={'product_bundle':product_bundle,'order':order})
                    for stock_move_create_datum in stock_move_create_data:
                        move = stock_move.create(cr, uid, stock_move_create_datum)


                        if order_line.move_dest_id and order_line.move_dest_id.state != 'done':
                              order_line.move_dest_id.write({'location_id': order.location_id.id})
                        todo_moves.append(move)
                    pass                          
                
                else:
                    move = stock_move.create(cr, uid, self._prepare_order_line_move(cr, uid, order, order_line, picking_id, context=context))
                    if order_line.move_dest_id and order_line.move_dest_id.state != 'done':
                        order_line.move_dest_id.write({'location_id': order.location_id.id})
                    todo_moves.append(move)
        stock_move.action_confirm(cr, uid, todo_moves)
        stock_move.force_assign(cr, uid, todo_moves)
        wf_service.trg_validate(uid, 'stock.picking', picking_id, 'button_confirm', cr)
        return [picking_id]