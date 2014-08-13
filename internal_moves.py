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
    


from openerp import netsvc

import time
from lxml import etree
from openerp.osv import fields, osv
from openerp.tools.misc import DEFAULT_SERVER_DATETIME_FORMAT
from openerp.tools.float_utils import float_compare
import openerp.addons.decimal_precision as dp
from openerp.tools.translate import _


class stock_move(osv.osv):
    _inherit="stock.move"
    _name="stock.move"
    
    _columns={
              'parent_id':fields.many2one('stock.move', 'Parent', required=False),
              'child_ids':fields.one2many('stock.move','parent_id','Childs',required=False)
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

class glimsol_stock_partial_picking(osv.osv_memory):
    _inherit = "stock.partial.picking"
    _name="stock.partial.picking"



    def default_get(self, cr, uid, fields, context=None):
        if context is None: context = {}
        res = super(glimsol_stock_partial_picking, self).default_get(cr, uid, fields, context=context)
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
            #reformat moves to disregard bundled
            moves = [self._partial_move_for(cr, uid, m) for m in picking.move_lines if m.state not in ('done','cancel') and m.product_id.supply_method != 'bundle']
            res.update(move_ids=moves)
        if 'date' in fields:
            res.update(date=time.strftime(DEFAULT_SERVER_DATETIME_FORMAT))
        return res    
        
class stock_picking(osv.osv):
    _inherit="stock.picking"
    _name="stock.picking"

    def do_partial(self, cr, uid, ids, partial_datas, context=None):
        """ Makes partial picking and moves done.
        @param partial_datas : Dictionary containing details of partial picking
                          like partner_id, partner_id, delivery_date,
                          delivery moves with product_id, product_qty, uom
        @return: Dictionary of values
        """
        print "stock_picking.do_partial".upper()
        if context is None:
            context = {}
        else:
            context = dict(context)
        res = {}
        move_obj = self.pool.get('stock.move')
        product_obj = self.pool.get('product.product')
        currency_obj = self.pool.get('res.currency')
        uom_obj = self.pool.get('product.uom')
        sequence_obj = self.pool.get('ir.sequence')
        wf_service = netsvc.LocalService("workflow")
        for pick in self.browse(cr, uid, ids, context=context):
            new_picking = None
            complete, too_many, too_few = [], [], []
            move_product_qty, prodlot_ids, product_avail, partial_qty, product_uoms = {}, {}, {}, {}, {}
            #reformat move_lines. Disregard bundled moves
#             for move in pick.move_lines:
            move_lines = [x for x in pick.move_lines if x.product_id.supply_method != 'bundle']
            for move in move_lines:
                if move.state in ('done', 'cancel'):
                    continue
                partial_data = partial_datas.get('move%s'%(move.id), {})
                product_qty = partial_data.get('product_qty',0.0)
                move_product_qty[move.id] = product_qty
                product_uom = partial_data.get('product_uom',False)
                product_price = partial_data.get('product_price',0.0)
                product_currency = partial_data.get('product_currency',False)
                prodlot_id = partial_data.get('prodlot_id')
                prodlot_ids[move.id] = prodlot_id
                product_uoms[move.id] = product_uom
                partial_qty[move.id] = uom_obj._compute_qty(cr, uid, product_uoms[move.id], product_qty, move.product_uom.id)
                if move.product_qty == partial_qty[move.id]:
                    complete.append(move)
                elif move.product_qty > partial_qty[move.id]:
                    too_few.append(move)
                else:
                    too_many.append(move)

                # Average price computation
                if (pick.type == 'in') and (move.product_id.cost_method == 'average'):
                    product = product_obj.browse(cr, uid, move.product_id.id)
                    move_currency_id = move.company_id.currency_id.id
                    context['currency_id'] = move_currency_id
                    qty = uom_obj._compute_qty(cr, uid, product_uom, product_qty, product.uom_id.id)

                    if product.id not in product_avail:
                        # keep track of stock on hand including processed lines not yet marked as done
                        product_avail[product.id] = product.qty_available

                    if qty > 0:
                        new_price = currency_obj.compute(cr, uid, product_currency,
                                move_currency_id, product_price, round=False)
                        new_price = uom_obj._compute_price(cr, uid, product_uom, new_price,
                                product.uom_id.id)
                        if product_avail[product.id] <= 0:
                            product_avail[product.id] = 0
                            new_std_price = new_price
                        else:
                            # Get the standard price
                            amount_unit = product.price_get('standard_price', context=context)[product.id]
                            new_std_price = ((amount_unit * product_avail[product.id])\
                                + (new_price * qty))/(product_avail[product.id] + qty)
                        # Write the field according to price type field
                        product_obj.write(cr, uid, [product.id], {'standard_price': new_std_price})

                        # Record the values that were chosen in the wizard, so they can be
                        # used for inventory valuation if real-time valuation is enabled.
                        move_obj.write(cr, uid, [move.id],
                                {'price_unit': product_price,
                                 'price_currency_id': product_currency})

                        product_avail[product.id] += qty



            for move in too_few:
                product_qty = move_product_qty[move.id]
                if not new_picking:
                    new_picking_name = pick.name
                    self.write(cr, uid, [pick.id], 
                               {'name': sequence_obj.get(cr, uid,
                                            'stock.picking.%s'%(pick.type)),
                               })
                    new_picking = self.copy(cr, uid, pick.id,
                            {
                                'name': new_picking_name,
                                'move_lines' : [],
                                'state':'draft',
                            })
                if product_qty != 0:
                    defaults = {
                            'product_qty' : product_qty,
                            'product_uos_qty': product_qty, #TODO: put correct uos_qty
                            'picking_id' : new_picking,
                            'state': 'assigned',
                            'move_dest_id': False,
                            'price_unit': move.price_unit,
                            'product_uom': product_uoms[move.id]
                    }
                    prodlot_id = prodlot_ids[move.id]
                    if prodlot_id:
                        defaults.update(prodlot_id=prodlot_id)
                    move_obj.copy(cr, uid, move.id, defaults)
                move_obj.write(cr, uid, [move.id],
                        {
                            'product_qty': move.product_qty - partial_qty[move.id],
                            'product_uos_qty': move.product_qty - partial_qty[move.id], #TODO: put correct uos_qty
                            'prodlot_id': False,
                            'tracking_id': False,
                        })

            if new_picking:
                move_obj.write(cr, uid, [c.id for c in complete], {'picking_id': new_picking})
            for move in complete:
                defaults = {'product_uom': product_uoms[move.id], 'product_qty': move_product_qty[move.id]}
                if prodlot_ids.get(move.id):
                    defaults.update({'prodlot_id': prodlot_ids[move.id]})
                move_obj.write(cr, uid, [move.id], defaults)
            for move in too_many:
                product_qty = move_product_qty[move.id]
                defaults = {
                    'product_qty' : product_qty,
                    'product_uos_qty': product_qty, #TODO: put correct uos_qty
                    'product_uom': product_uoms[move.id]
                }
                prodlot_id = prodlot_ids.get(move.id)
                if prodlot_ids.get(move.id):
                    defaults.update(prodlot_id=prodlot_id)
                if new_picking:
                    defaults.update(picking_id=new_picking)
                move_obj.write(cr, uid, [move.id], defaults)

            # At first we confirm the new picking (if necessary)
            if new_picking:
                wf_service.trg_validate(uid, 'stock.picking', new_picking, 'button_confirm', cr)
                # Then we finish the good picking
                self.write(cr, uid, [pick.id], {'backorder_id': new_picking})
                self.action_move(cr, uid, [new_picking], context=context)
                wf_service.trg_validate(uid, 'stock.picking', new_picking, 'button_done', cr)
                wf_service.trg_write(uid, 'stock.picking', pick.id, cr)
                delivered_pack_id = pick.id
                back_order_name = self.browse(cr, uid, delivered_pack_id, context=context).name
                self.message_post(cr, uid, new_picking, body=_("Back order <em>%s</em> has been <b>created</b>.") % (back_order_name), context=context)
            else:
                self.action_move(cr, uid, [pick.id], context=context)
                wf_service.trg_validate(uid, 'stock.picking', pick.id, 'button_done', cr)
                delivered_pack_id = pick.id

            delivered_pack = self.browse(cr, uid, delivered_pack_id, context=context)
            res[pick.id] = {'delivered_picking': delivered_pack.id or False}

        return res
    
    def onchange_move_lines(self, cr, uid, ids, move_lines,context=None):
        print "onchange_move_lines".upper()
        
        
        return True
