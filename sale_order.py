
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


class sale_order(osv.osv):
    _name = "sale.order"
    _inherit = "sale.order"
    
    def _create_pickings_and_procurements(self, cr, uid, order, order_lines, picking_id=False, context=None):
        """Create the required procurements to supply sales order lines, also connecting
        the procurements to appropriate stock moves in order to bring the goods to the
        sales order's requested location.

        If ``picking_id`` is provided, the stock moves will be added to it, otherwise
        a standard outgoing picking will be created to wrap the stock moves, as returned
        by :meth:`~._prepare_order_picking`.

        Modules that wish to customize the procurements or partition the stock moves over
        multiple stock pickings may override this method and call ``super()`` with
        different subsets of ``order_lines`` and/or preset ``picking_id`` values.

        :param browse_record order: sales order to which the order lines belong
        :param list(browse_record) order_lines: sales order line records to procure
        :param int picking_id: optional ID of a stock picking to which the created stock moves
                               will be added. A new picking will be created if ommitted.
        :return: True
        """
        move_obj = self.pool.get('stock.move')
        picking_obj = self.pool.get('stock.picking')
        procurement_obj = self.pool.get('procurement.order')
        proc_ids = []
        
        location_id = order.shop_id.warehouse_id.lot_stock_id.id
        output_id = order.shop_id.warehouse_id.lot_output_id.id

        for line in order_lines:
            if line.state == 'done':
                continue

            date_planned = self._get_date_planned(cr, uid, order, line, order.date_order, context=context)
            
            fake_line_ids = []
            is_bundle = False
            
            if line.product_id:
                if line.product_id.supply_method == 'bundle':
                    fake_line_ids = filter(None, map(lambda x:x, line.product_id.item_ids))
                    is_bundle = True
                else:
                    fake_line_ids.append(line)
                
                for fake_line in fake_line_ids:
                    line_vals = {}
                    
                    line_vals.update({
                        'location_id': location_id,
                        'company_id': order.company_id.id,                        
                        #move
                        'location_dest_id': output_id,
                        'date': date_planned,
                        'date_expected': date_planned,
                        'partner_id': line.address_allotment_id.id or order.partner_shipping_id.id,
                        'sale_line_id': line.id,
                        'origin': order.name,
                        'tracking_id': False,
                        'state': 'draft',
                    })
                    
                    if is_bundle:
                        line_vals.update({
                            'product_id': fake_line.item_id.id,
                            'product_qty': fake_line.qty_uom*line.product_uom_qty,
                            'product_uom': fake_line.uom_id.id,
                            'product_uos_qty': fake_line.qty_uom,
                            'product_uos': fake_line.uom_id.id,
                            'procure_method': fake_line.item_id.procure_method,
                            'price_unit': fake_line.item_id.standard_price or 0.0,
                            'name': fake_line.item_id.name,
                            'note': fake_line.item_id.name + ' (' + line.name + ')',
                        })
                        product_id = fake_line.item_id
                    else:
                        line_vals.update({
                            'name': line.name,
                            'note': line.name,
                            'product_id': line.product_id.id,
                            'product_qty': line.product_uom_qty,
                            'product_uom': line.product_uom.id,
                            'product_uos_qty': (line.product_uos and line.product_uos_qty) or line.product_uom_qty,
                            'product_uos': (line.product_uos and line.product_uos.id) or line.product_uom.id,
                            'procure_method': line.type,
                            'product_packaging': line.product_packaging,
                            'price_unit': line.product_id.standard_price or 0.0,
                        })
                        product_id = line.product_id
                    
                    
                    if product_id.type in ('product', 'consu'):
                        if not picking_id:
                            picking_id = picking_obj.create(cr, uid, self._prepare_order_picking(cr, uid, order, context=context))
                        line_vals.update({'picking_id': picking_id,})
                        move_id = move_obj.create(cr, uid, line_vals)
                    else:
                        # a service has no stock move
                        move_id = False
                    
                    del line_vals['location_dest_id']
                    del line_vals['date']
                    del line_vals['date_expected']
                    del line_vals['picking_id']
                    del line_vals['partner_id']
                    del line_vals['sale_line_id']
                    del line_vals['tracking_id']
                    del line_vals['state']
                    
                    line_vals.update({
                        'move_id': move_id,
                        'date_planned': date_planned,
                    })
                    
                    proc_id = procurement_obj.create(cr, uid, line_vals)
                    proc_ids.append(proc_id)
                    line.write({'procurement_id': proc_id})
                    self.ship_recreate(cr, uid, order, line, move_id, proc_id)

        wf_service = netsvc.LocalService("workflow")
        if picking_id:
            wf_service.trg_validate(uid, 'stock.picking', picking_id, 'button_confirm', cr)
        for proc_id in proc_ids:
            wf_service.trg_validate(uid, 'procurement.order', proc_id, 'button_confirm', cr)

        val = {}
        if order.state == 'shipping_except':
            val['state'] = 'progress'
            val['shipped'] = False

            if (order.order_policy == 'manual'):
                for line in order.order_line:
                    if (not line.invoiced) and (line.state not in ('cancel', 'draft')):
                        val['state'] = 'manual'
                        break
        order.write(val)
        return True
    
    
#     def process_product(self,cr,uid,line,product_id,product_qty,result=None,context=None):
#         
#         fake_line_ids = []
#         is_bundle = False        
#         location_id = context['location_id']
#         order = context['order']
#         output_id= context['output_id']
#         date_planned=context['date_planned']
#         picking_id=context['picking_id']
#         picking_obj=context['picking_obj']
#         move_obj=context['move_obj']
#         procurement_obj=context['procurement_obj']
#         proc_ids=context['proc_ids']
#         
#         if product_id.supply_method == 'bundle':
#             fake_line_ids = filter(None, map(lambda x:x, product_id.item_ids))
#             is_bundle = True
#         else:
#             fake_line_ids.append(line)
#         
#         for fake_line in fake_line_ids:
#             line_vals = {}
#             
#             line_vals.update({
#                 'location_id': location_id,
#                 'company_id': order.company_id.id,                        
#                 #move
#                 'location_dest_id': output_id,
#                 'date': date_planned,
#                 'date_expected': date_planned,
#                 'partner_id': line.address_allotment_id.id or order.partner_shipping_id.id,
#                 'sale_line_id': line.id,
#                 'origin': order.name,
#                 'tracking_id': False,
#                 'state': 'draft',
#             })
# 
#             if is_bundle:
#                 context.update({
#                     'product_id': fake_line.item_id.id,
#                     'product_qty': fake_line.qty_uom * product_qty,
#                     'product_uom': fake_line.uom_id.id,
#                     'product_uos_qty': fake_line.qty_uom * product_qty,
#                     'product_uos': fake_line.uom_id.id,
#                     'procure_method': fake_line.item_id.procure_method,
#                     'price_unit': fake_line.item_id.standard_price or 0.0,
#                     'name': fake_line.item_id.name,
#                     'note': fake_line.item_id.name + ' (' + line.name + ')',
#                 })
#                 picking_id,proc_ids=self.process_product(cr, uid, line, fake_line.item_id, fake_line.qty_uom * product_qty, context=context)
#                 continue
# #                 line_vals.update({
# #                     'product_id': fake_line.item_id.id,
# #                     'product_qty': fake_line.qty_uom * line.product_uom_qty,
# #                     'product_uom': fake_line.uom_id.id,
# #                     'product_uos_qty': fake_line.qty_uom * line.product_uos_qty,
# #                     'product_uos': fake_line.uom_id.id,
# #                     'procure_method': fake_line.item_id.procure_method,
# #                     'price_unit': fake_line.item_id.standard_price or 0.0,
# #                     'name': fake_line.item_id.name,
# #                     'note': fake_line.item_id.name + ' (' + line.name + ')',
# #                 })
# #                 product_id = fake_line.item_id
#             else:
#                 line_vals.update({
#                     'name': line.name,
#                     'note': line.name,
#                     'product_id': line.product_id.id,
#                     'product_qty': line.product_uom_qty,
#                     'product_uom': line.product_uom.id,
#                     'product_uos_qty': (line.product_uos and line.product_uos_qty) or line.product_uom_qty,
#                     'product_uos': (line.product_uos and line.product_uos.id) or line.product_uom.id,
#                     'procure_method': line.type,
#                     'product_packaging': line.product_packaging,
#                     'price_unit': line.product_id.standard_price or 0.0,
#                 })
#                 product_id = product_id
#                 
#                 if sorted(set(['name', 'note', 'product_id', 'product_qty', 'product_uom', 'product_uos_qty', 'product_uos', 'procure_method', 'product_packaging', 'price_unit'])) == sorted(set(['name', 'note', 'product_id', 'product_qty', 'product_uom', 'product_uos_qty', 'product_uos', 'procure_method', 'product_packaging', 'price_unit']).intersection(set(line_vals.keys()))):
#                     line_vals['name']=context['name']
#                     line_vals['product_id']=context['product_id']
#                     line_vals['product_qty']=context['product_qty']
#                     line_vals['product_uos_qty']=context['product_qty']
#                     line_vals['product_uom']=context['product_uom']
#                     line_vals['product_uos']=context['product_uos']
#                     line_vals['procure_method']=context['procure_method']
#                     line_vals['price_unit']=context['price_unit']
#                     line_vals['note']=context['note']
#                     
#             
#             if product_id.type in ('product', 'consu'):
#                 if not picking_id:
#                     picking_id = picking_obj.create(cr, uid, self._prepare_order_picking(cr, uid, order, context=context))
#                     context['picking_id']=picking_id
#                 line_vals.update({'picking_id': picking_id,})
#                 move_id = move_obj.create(cr, uid, line_vals)
#             else:
#                 # a service has no stock move
#                 move_id = False
#             
#             del line_vals['location_dest_id']
#             del line_vals['date']
#             del line_vals['date_expected']
#             del line_vals['picking_id']
#             del line_vals['partner_id']
#             del line_vals['sale_line_id']
#             del line_vals['tracking_id']
#             del line_vals['state']
#             
#             line_vals.update({
#                 'move_id': move_id,
#                 'date_planned': date_planned,
#             })
#             
#             proc_id = procurement_obj.create(cr, uid, line_vals)
#             proc_ids.append(proc_id)
#             line.write({'procurement_id': proc_id})
#             self.ship_recreate(cr, uid, order, line, move_id, proc_id)
#         return picking_id,proc_ids
#     
#     def _create_pickings_and_procurements(self, cr, uid, order, order_lines, picking_id=False, context=None):
#         """Create the required procurements to supply sales order lines, also connecting
#         the procurements to appropriate stock moves in order to bring the goods to the
#         sales order's requested location.
# 
#         If ``picking_id`` is provided, the stock moves will be added to it, otherwise
#         a standard outgoing picking will be created to wrap the stock moves, as returned
#         by :meth:`~._prepare_order_picking`.
# 
#         Modules that wish to customize the procurements or partition the stock moves over
#         multiple stock pickings may override this method and call ``super()`` with
#         different subsets of ``order_lines`` and/or preset ``picking_id`` values.
# 
#         :param browse_record order: sales order to which the order lines belong
#         :param list(browse_record) order_lines: sales order line records to procure
#         :param int picking_id: optional ID of a stock picking to which the created stock moves
#                                will be added. A new picking will be created if ommitted.
#         :return: True
#         """
#         move_obj = self.pool.get('stock.move')
#         picking_obj = self.pool.get('stock.picking')
#         procurement_obj = self.pool.get('procurement.order')
#         proc_ids = []
#         
#         location_id = order.shop_id.warehouse_id.lot_stock_id.id
#         output_id = order.shop_id.warehouse_id.lot_output_id.id
# 
#         for line in order_lines:
#             if line.state == 'done':
#                 continue
# 
#             date_planned = self._get_date_planned(cr, uid, order, line, order.date_order, context=context)
#             
# #             fake_line_ids = []
# #             is_bundle = False
#             
#             if line.product_id:
#                 temp_context={
#                     'name': line.name,
#                     'note': line.name,
#                     'product_id': line.product_id.id,
#                     'product_qty': line.product_uom_qty,
#                     'product_uom': line.product_uom.id,
#                     'product_uos_qty': (line.product_uos and line.product_uos_qty) or line.product_uom_qty,
#                     'product_uos': (line.product_uos and line.product_uos.id) or line.product_uom.id,
#                     'procure_method': line.type,
#                     'product_packaging': line.product_packaging,
#                     'price_unit': line.product_id.standard_price or 0.0,
#                     'proc_ids':proc_ids,'procurement_obj':procurement_obj,'location_id':location_id,'order':order,'output_id':output_id,'date_planned':date_planned,'picking_id':picking_id,'picking_obj':picking_obj,'move_obj':move_obj,                    
#                 }
#                 if not context:
#                     context = temp_context
#                 else:
#                     context.update(temp_context)
#                 picking_id,proc_ids=self.process_product(cr,uid,line,line.product_id,line.product_uom_qty,context=context)
# 
#         wf_service = netsvc.LocalService("workflow")
#         if picking_id:
#             wf_service.trg_validate(uid, 'stock.picking', picking_id, 'button_confirm', cr)
#         for proc_id in proc_ids:
#             wf_service.trg_validate(uid, 'procurement.order', proc_id, 'button_confirm', cr)
# 
#         val = {}
#         if order.state == 'shipping_except':
#             val['state'] = 'progress'
#             val['shipped'] = False
# 
#             if (order.order_policy == 'manual'):
#                 for line in order.order_line:
#                     if (not line.invoiced) and (line.state not in ('cancel', 'draft')):
#                         val['state'] = 'manual'
#                         break
#         order.write(val)
#         return True