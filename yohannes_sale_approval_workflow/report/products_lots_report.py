from odoo import models, api

class ProductsLotsReport(models.AbstractModel):
    _name = 'report.yohannes_sale_approval_workflow.products_lots'
    _description = 'Products Lots Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        price_type = data['form']['price_type']
        quant_ids = data.get('quant_ids', [])

        if quant_ids:
            quants = self.env['stock.quant'].search([('id', 'in', quant_ids)])
        else:
            quants = self.env['stock.quant'].search([
                ('location_id.usage', '=', 'internal'),
                ('quantity', '>', 0)
            ])

        # Group by product
        product_data = {}
        for q in quants:
            product = q.product_id
            if product.id not in product_data:
                # Determine unit price based on selection
                if price_type == 'wholesale':
                    unit_price = product.product_tmpl_id.wholesale_price
                else:
                    unit_price = product.product_tmpl_id.retail_price

                product_data[product.id] = {
                    'product_name': product.name,
                    'unit_price': unit_price,
                    'expiry_dates': set()
                }

            if q.lot_id and q.lot_id.expiration_date:
                product_data[product.id]['expiry_dates'].add(q.lot_id.expiration_date.strftime('%d/%m/%Y'))
            else:
                product_data[product.id]['expiry_dates'].add('')

        # Prepare final list
        products_list = []
        sn = 1
        for pid, data_dict in product_data.items():
            expiry_dates_list = sorted(list(data_dict['expiry_dates']), reverse=True)
            products_list.append({
                'sn': sn,
                'product_name': data_dict['product_name'],
                'unit_price': data_dict['unit_price'],
                'expiry_dates_list': expiry_dates_list,
            })
            sn += 1

        return {
            'doc_ids': docids,
            'doc_model': 'products.lots.report.wizard',
            'docs': self.env['products.lots.report.wizard'].browse(docids),
            'price_type_label': 'Product Pricelist with Ex Date for wholesalers' if price_type == 'wholesale' else 'Product Pricelist with Ex Date for retailers',
            'products': products_list,
        }
