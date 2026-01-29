frappe.listview_settings['Online Store'] = {
  add_fields: ['store_type', 'shop_logo_url', 'region', 'shop_id'],

  hide_name_column: true,

  onload(listview) {
    listview.page.add_inner_button('Sync', () => {
      frappe.msgprint('Sync clicked');
    });
  },

  formatters: {
    store_type(val) {
      const v = (val || '').toLowerCase();

      const wrap = (src, title) => `
          <img src="${src}" alt="${title}" style="height:32px;width:32px;object-fit:contain;" />
      `;

      if (v.includes('shopee')) return wrap('/assets/online_store_integration/images/shopee.png', 'Shopee');
      if (v.includes('lazada')) return wrap('/assets/online_store_integration/images/lazada.svg', 'Lazada');
      return val || '';
    },

    // ✅ This is your "new ID column"
    store_card(_val, df, doc) {
      // Make sure it renders as HTML
      df.fieldtype = 'HTML';

      const title = frappe.utils.escape_html(doc.shop_id || '');
      const region = frappe.utils.escape_html(doc.region || '');
      const logo = doc.shop_logo_url || '';

      // Your doctype route (based on your screenshot)
      const href = `/app/online-store/${encodeURIComponent(doc.name)}`;

      const logoHtml = logo
        ? `<img src="${logo}" alt=""
                style="height:28px;width:28px;border-radius:6px;object-fit:contain;flex:0 0 auto;" />`
        : `<span style="height:28px;width:28px;border-radius:6px;background:var(--control-bg);display:inline-block;flex:0 0 auto;"></span>`;

      return `
        <a href="${href}" style="display:flex;gap:10px;align-items:center;text-decoration:none;min-width:0;">
          ${logoHtml}
          <span style="display:flex;flex-direction:column;min-width:0;">
            <span class="ellipsis" style="font-weight:600;line-height:1.2;">${title}</span>
            <span class="ellipsis text-muted" style="font-size:12px;line-height:1.2;">${region}</span>
          </span>
        </a>
      `;
    }
  }
};
