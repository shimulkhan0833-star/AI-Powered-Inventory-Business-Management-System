"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
const money = value => `৳${Number(value || 0).toLocaleString("en-BD", {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
const reference = (prefix, id) => `${prefix}-${String(id).padStart(5, "0")}`;
const purchaseDateTime = value => value ? String(value).replace("T", " ").slice(0, 19) : "—";
function movementReason(movement) {
  const reason = movement.reason || "";
  if (movement.movement_type === "purchase") return reason.replace(/^Purchase #(\d+)$/, (_, id) => `Purchase ${reference("PUR", id)}`);
  if (movement.movement_type === "sale") return reason.replace(/^Sale #(\d+)$/, (_, id) => `Sale ${reference("INV", id)}`);
  return reason;
}
const state = {user:null, page:"dashboard", products:[], customers:[], sales:[], purchases:[], employees:[]};
const modal = $("#modal");
let toastTimer;
let memoPreviewUrl = null;

function clearMemoPreview() {
  if (memoPreviewUrl) URL.revokeObjectURL(memoPreviewUrl);
  memoPreviewUrl = null;
  modal.classList.remove("memo-review-modal");
  modal.classList.remove("sale-modal");
}
modal.addEventListener("close", clearMemoPreview);

function notify(message, error = false) {
  const el = $("#notice"); el.textContent = message; el.classList.toggle("error", error); el.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.hidden = true; }, 5500);
}
async function api(path, options = {}) {
  const headers = {...options.headers};
  if (options.json !== undefined) headers["Content-Type"] = "application/json";
  let response;
  try { response = await fetch(path, {method: options.method || "GET", credentials:"same-origin", headers, body: options.json !== undefined ? JSON.stringify(options.json) : options.body}); }
  catch { throw new Error("Connection lost. Please check your internet and try again."); }
  if (!response.ok) {
    let detail; try { detail = (await response.json()).detail; } catch { /* No JSON body. */ }
    throw new Error(typeof detail === "string" ? detail : "Please check the details and try again.");
  }
  return response.status === 204 ? null : response.json();
}
function formObject(form) { return Object.fromEntries(new FormData(form).entries()); }
function openModal(title, body, eyebrow = "OLEYN STOCK") {
  clearMemoPreview();
  $("#modal-title").textContent = title; $("#modal-eyebrow").textContent = eyebrow;
  $("#modal-body").innerHTML = body; if (!modal.open) modal.showModal();
}
function closeModal() { if (modal.open) modal.close(); }
function actions(label = "Save") { return `<div class="modal-actions"><button type="button" class="btn" data-action="close">Cancel</button><button type="submit" class="btn primary">${esc(label)}</button></div>`; }
function table(headers, rows, empty) {
  if (!rows.length) return `<div class="empty">${esc(empty)}</div>`;
  return `<div class="table-wrap"><table><thead><tr>${headers.map(h => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
}
function pageHeader(kicker, title, description, buttons = "") {
  $("#page-heading").innerHTML = `<div class="page-title"><div><span class="eyebrow">${esc(kicker)}</span><h1>${esc(title)}</h1><p>${esc(description)}</p></div><div class="actions">${buttons}</div></div>`;
}
function button(label, action, primary = false, extra = "") { return `<button class="btn ${primary ? "primary" : ""}" data-action="${action}" ${extra}>${esc(label)}</button>`; }
function showAuth(which = "login") {
  $("#auth").hidden = false; $("#workspace").hidden = true;
  $("#login-panel").hidden = which !== "login"; $("#register-panel").hidden = which !== "register";
  $$(".auth-tabs button").forEach(el => el.classList.toggle("active", el.dataset.auth === which));
}
async function startWorkspace(user) {
  state.user = user; $("#auth").hidden = true; $("#workspace").hidden = false;
  $("#business-label").textContent = user.business_name; $("#user-label").textContent = user.name; $("#role-label").textContent = user.role;
  $$(".owner-only").forEach(el => {el.hidden = user.role !== "owner";});
  await navigate("dashboard");
}
async function loadData() {
  const tasks = [api("/products"), api("/customers"), api("/sales")];
  if (state.user.role === "owner") tasks.push(api("/purchases"), api("/employees"));
  const [products, customers, sales, purchases = [], employees = []] = await Promise.all(tasks);
  Object.assign(state, {products, customers, sales, purchases, employees});
}
async function navigate(page) {
  if (!state.user) return;
  if (state.user.role !== "owner" && ["purchases", "employees"].includes(page)) page = "dashboard";
  state.page = page; $$("[data-page]").forEach(el => el.classList.toggle("active", el.dataset.page === page));
  $("#page-content").innerHTML = `<div class="card muted">Loading your workspace…</div>`;
  try { await loadData(); renderPage(); } catch (error) { $("#page-content").innerHTML = `<div class="card">${esc(error.message)} <button class="text-button" data-action="refresh">Try again</button></div>`; }
}
function renderPage() {
  const owner = state.user.role === "owner";
  const productRows = state.products.map(p => `<tr><td><div class="product-cell">${p.has_image ? `<img class="product-image" src="/products/${p.product_id}/image" alt="">` : `<span class="product-image product-image-placeholder" aria-hidden="true">◇</span>`}<span><strong>${esc(p.name)}</strong><small>${esc(p.sku)}</small></span></div></td><td>${money(p.selling_price)}</td>${owner ? `<td>${p.purchase_cost == null ? "—" : money(p.purchase_cost)}</td>` : ""}<td><span class="pill ${p.stock_quantity <= 5 ? "warn" : ""}">${p.stock_quantity} in stock</span></td><td><button class="text-button" data-action="history" data-id="${p.product_id}">History</button>${owner ? ` &nbsp; <button class="text-button" data-action="edit-product" data-id="${p.product_id}">Edit</button> &nbsp; <button class="text-button" data-action="adjust" data-id="${p.product_id}">Adjust</button>` : ""}</td></tr>`);
  const salesRows = state.sales.map(s => `<tr><td><strong>${reference("INV", s.invoice_id)}</strong><small>${esc((s.created_at || "").slice(0,10))}</small></td><td>${esc(s.customer_name)}</td><td>${money(s.total)}</td><td>${money(s.due)}</td><td><a href="/sales/${s.invoice_id}/print" target="_blank" rel="noopener">View invoice</a>${Number(s.due) > 0 ? ` &nbsp; <button class="text-button" data-action="payment" data-id="${s.invoice_id}">Add payment</button>` : ""}</td></tr>`);
  let html = "";
  if (state.page === "dashboard") {
    pageHeader("YOUR WORKSPACE", `Good to see you, ${state.user.name.split(" ")[0]}`, "Here’s a little clarity for your day.");
    const due = state.customers.reduce((sum, c) => sum + Number(c.due), 0);
    html = `<div class="hero"><div><span class="eyebrow">YOUR BUSINESS, AT A GLANCE</span><h2>Ready for a good day of business?</h2><p>Keep track of what’s on your shelves and what your customers owe, all in one place.</p></div><div class="hero-art" aria-hidden="true">✳</div></div>
      <div class="stats"><div class="stat"><small>Products</small><strong>${state.products.length}</strong><span>In your catalogue</span></div><div class="stat"><small>Outstanding dues</small><strong>${money(due)}</strong><span>Across ${state.customers.length} customers</span></div><div class="stat"><small>Sales invoices</small><strong>${state.sales.length}</strong><span>Recorded so far</span></div></div>
      <div class="card"><div class="card-head"><div><h3>A good place to start</h3><p>Jump back into the things you do most.</p></div></div><div class="quick-grid"><button class="quick" data-action="new-sale"><span class="symbol">▤</span><b>Make a sale</b><small>Create an invoice for a customer.</small></button><button class="quick" data-page="products"><span class="symbol">◇</span><b>Check your stock</b><small>See what’s on your shelves.</small></button><button class="quick" data-page="customers"><span class="symbol">◉</span><b>View customer dues</b><small>Keep up with outstanding balances.</small></button></div></div>
      <div class="card"><div class="card-head"><div><h3>Recent sales</h3><p>Your latest invoices.</p></div><button class="text-button" data-page="sales">View all</button></div>${table(["Invoice","Customer","Total","Due",""], salesRows.slice(0,5), "No sales yet. Your first invoice will appear here.")}</div>`;
  } else if (state.page === "products") {
    pageHeader("YOUR INVENTORY", "Products & stock", "Keep your catalogue and quantities up to date.", owner ? button("+ Add product", "new-product", true) : "");
    html = `<div class="card"><div class="card-head"><div><h3>Product catalogue</h3><p>${state.products.length} products in your business</p></div></div><div class="toolbar"><input id="product-search" type="search" placeholder="Search by name or SKU" aria-label="Search products"></div><div id="product-table">${table(["Product","Selling price",...(owner?["Purchase cost"]:[]),"Available",""],productRows,"No products yet.")}</div></div>`;
  } else if (state.page === "purchases") {
    pageHeader("STOCK COMING IN", "Purchases", "Record what arrives from your suppliers.", button("Scan memo", "memo") + button("+ New purchase", "new-purchase", true));
    const rows = state.purchases.map(p => `<tr><td><strong>${reference("PUR", p.purchase_id)}</strong><small>${esc(purchaseDateTime(p.created_at))}</small></td><td>${esc(p.supplier_name || "Not specified")}</td><td>${p.items.length} item(s)</td><td>${money(p.total)}</td></tr>`);
    html = `<div class="card"><div class="card-head"><div><h3>Purchase history</h3><p>Every saved purchase adds to stock.</p></div></div>${table(["Purchase","Supplier","Items","Total"],rows,"No purchases yet. Add one manually or scan a memo.")}</div>`;
  } else if (state.page === "sales") {
    pageHeader("YOUR TRANSACTIONS", "Sales", "Create invoices and keep track of payments.", button("+ New sale", "new-sale", true));
    html = `<div class="card"><div class="card-head"><div><h3>Sales invoices</h3><p>Review invoices and record payments.</p></div></div>${table(["Invoice","Customer","Total","Due",""],salesRows,"No sales yet. Create your first invoice.")}</div>`;
  } else if (state.page === "customers") {
    pageHeader("YOUR CUSTOMERS", "Customers & dues", "Keep your customer balances in view.", button("+ Add customer", "new-customer", true));
    const rows = state.customers.map(c => `<tr><td><strong>${esc(c.name)}</strong></td><td>${esc(c.phone || "—")}</td><td>${money(c.due)}</td></tr>`);
    html = `<div class="card"><div class="card-head"><div><h3>Customer list</h3><p>Use the Sales page to record a payment against an invoice.</p></div></div>${table(["Customer","Phone","Outstanding due"],rows,"No customers yet.")}</div>`;
  } else if (state.page === "employees") {
    pageHeader("YOUR PEOPLE", "Team", "Manage access to your business.", button("+ Add salesperson", "new-employee", true));
    const rows = state.employees.map(u => `<tr><td><strong>${esc(u.name)}</strong><small>${esc(u.email)}</small></td><td>Salesperson</td><td><span class="pill ${u.is_active ? "" : "warn"}">${u.is_active ? "Active" : "Inactive"}</span></td><td>${u.is_active ? `<button class="text-button" data-action="deactivate" data-id="${u.user_id}">Deactivate</button>` : "—"}</td></tr>`);
    html = `<div class="card"><div class="card-head"><div><h3>Your salespeople</h3><p>Only owners can add and deactivate team members.</p></div></div>${table(["Name","Role","Status",""],rows,"No salespeople added yet.")}</div>`;
  }
  $("#page-content").innerHTML = html;
}

function productOptions(selected = "", placeholder = "Select a product") { return `<option value="">${esc(placeholder)}</option>` + state.products.map(p => `<option value="${p.product_id}" ${String(p.product_id) === String(selected) ? "selected" : ""}>${esc(p.name)} · ${esc(p.sku)} (${p.stock_quantity} available)</option>`).join(""); }
function customerOptions() { return `<option value="">Select a customer</option>` + state.customers.map(c => `<option value="${c.customer_id}">${esc(c.name)}</option>`).join(""); }
function matchMemoProduct(name) {
  const normalize = value => String(value ?? "").normalize("NFKC").trim().replace(/\s+/g, " ").toLowerCase();
  const memoName = normalize(name);
  if (!memoName) return null;
  const matches = state.products.filter(product => normalize(product.name) === memoName);
  return matches.length === 1 ? matches[0] : null;
}
function memoUnitCost(value) {
  if (value == null) return "";
  let text = String(value).trim().replace(/[০-৯]/g, digit => String(digit.charCodeAt(0) - 0x09e6));
  text = text.replace(/^(?:৳|tk\.?|bdt)\s*/i, "").replace(/\s*(?:৳|tk\.?|bdt)$/i, "").trim();
  if (!/^(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})+,\d{3})(?:\.\d{1,2})?$/.test(text)) return "";
  return text.replace(/,/g, "");
}
function purchaseRow(hint = {}) { const cost = memoUnitCost(hint.unit_price); const product = matchMemoProduct(hint.product_name); return `<div class="line-row"><label>Product<select name="product_id" required>${productOptions(product?.product_id ?? "", hint.product_name || "Select a product")}</select>${hint.product_name && !product ? `<small>No unique match for ${esc(hint.product_name)}. Select a product.</small>` : ""}</label><label>Quantity<input name="quantity" type="number" min="1" step="1" value="${esc(hint.quantity || "")}" required></label><label>Unit cost ৳${hint.unit_price != null && !cost ? `<small>Memo: ${esc(hint.unit_price)} — enter cost manually</small>` : ""}<input name="unit_price" type="number" min="0" step="0.01" value="${esc(cost)}" required></label><button type="button" class="icon-button" data-action="remove-line" aria-label="Remove item">×</button></div>`; }
function saleProductCard(p) {
  const picture = p.has_image ? `<img src="/products/${p.product_id}/image" alt="">` : `<span class="sale-card-placeholder" aria-hidden="true">◇</span>`;
  return `<article class="sale-product" data-search="${esc(`${p.name} ${p.sku}`.toLowerCase())}"><div class="sale-card-image">${picture}</div><strong class="sale-card-price">${money(p.selling_price)}</strong><span class="sale-card-name">${esc(p.name)}</span><small>${p.stock_quantity > 0 ? `${p.stock_quantity} available` : "Out of stock"}</small><button type="button" class="sale-add" data-action="add-sale-product" data-id="${p.product_id}" aria-label="Add ${esc(p.name)}" ${p.stock_quantity > 0 ? "" : "disabled"}>+</button></article>`;
}
function saleRow(p) { return `<div class="line-row sale-cart-line" data-id="${p.product_id}"><input name="product_id" type="hidden" value="${p.product_id}"><div class="sale-cart-product"><strong>${esc(p.name)}</strong><small>${money(p.selling_price)} each</small></div><label>Qty<input name="quantity" type="number" min="1" max="${p.stock_quantity}" step="1" value="1" required aria-label="Quantity for ${esc(p.name)}"></label><button type="button" class="icon-button" data-action="remove-sale-line" aria-label="Remove ${esc(p.name)}">×</button></div>`; }
function updateSaleTotals() {
  const form = $("#sale-form"); if (!form) return;
  const totalCents = $$(".sale-cart-line", form).reduce((sum, row) => {
    const p = state.products.find(item => item.product_id === Number(row.dataset.id));
    const qty = Number($("[name=quantity]", row).value);
    return sum + (p && Number.isSafeInteger(qty) && qty > 0 ? Math.round(Number(p.selling_price) * 100) * qty : 0);
  }, 0);
  const payment = $("[name=initial_payment]", form);
  const paidCents = Math.round((Number(payment.value) || 0) * 100);
  payment.max = (totalCents / 100).toFixed(2);
  $("#sale-total", form).textContent = money(totalCents / 100);
  $("#sale-paid", form).textContent = money(paidCents / 100);
  $("#sale-due", form).textContent = money(Math.max(0, totalCents - paidCents) / 100);
  $("#sale-empty", form).hidden = $$(".sale-cart-line", form).length > 0;
}
function addSaleProduct(id) {
  const product = state.products.find(p => p.product_id === id);
  if (!product || product.stock_quantity <= 0) return;
  const lines = $("#sale-lines"); const existing = $$(".sale-cart-line", lines).find(row => Number(row.dataset.id) === id);
  if (existing) {
    const input = $("[name=quantity]", existing);
    if (Number(input.value) >= product.stock_quantity) { notify("No more stock is available for this product.", true); return; }
    input.value = String((Number(input.value) || 0) + 1);
  } else {
    if ($$(".sale-cart-line", lines).length >= 100) { notify("A sale can contain at most 100 products.", true); return; }
    lines.insertAdjacentHTML("beforeend", saleRow(product));
  }
  updateSaleTotals();
}
function productForm(product = null) {
  const p = product || {}; const edit = !!product;
  openModal(edit ? "Edit product" : "Add a product", `<p class="muted">${edit ? "Update your product details." : "Start with the basics. You can adjust stock later."}</p><form id="product-form" data-id="${p.product_id || ""}" class="form-stack"><div class="form-grid"><label class="full">Product name<input name="name" value="${esc(p.name || "")}" maxlength="150" required></label><label class="full">Product image <small>Optional · JPEG or PNG, up to 2 MB${p.has_image ? " · Choose a file to replace the current image" : ""}</small><input name="image" type="file" accept="image/jpeg,image/png"></label><label>SKU <small>Leave blank to generate</small><input name="sku" value="${esc(p.sku || "")}" maxlength="64"></label><label>Selling price ৳<input name="selling_price" type="number" min="0" step="0.01" value="${esc(p.selling_price || "")}" required></label><label>Purchase cost ৳ <small>Only visible to owners</small><input name="purchase_cost" type="number" min="0" step="0.01" value="${esc(p.purchase_cost ?? "")}"></label>${edit ? "" : `<label>Opening stock<input name="opening_stock" type="number" min="0" step="1" value="0" required></label>`}</div>${actions(edit ? "Save changes" : "Add product")}</form>`, "PRODUCTS & STOCK");
}
function purchaseForm(draft = null, memoFile = null) {
  if (!state.products.length) { notify("Add a product before recording a purchase.", true); return; }
  const rows = draft?.items?.length ? draft.items.map(purchaseRow).join("") : purchaseRow();
  const form = `${draft ? `<p class="info warning">Review every extracted field and select the matching product. Nothing has been saved yet.</p>` : `<p class="muted">Record the items you received. Stock updates when you save.</p>`}<form id="purchase-form" class="form-stack"><label>Supplier name <small>Optional</small><input name="supplier_name" maxlength="150" value="${esc(draft?.supplier_name || "")}"></label><div><label>Purchase items</label><div id="purchase-lines">${rows}</div><button type="button" class="text-button" data-action="add-purchase-line">+ Add another item</button></div>${actions("Save purchase")}</form>`;
  const content = memoFile ? `<div class="memo-review"><section class="memo-preview" aria-label="Uploaded memo"><h3>Uploaded memo</h3><div class="memo-preview-image"><img id="memo-preview-image" alt="Uploaded purchase memo"></div></section><div class="memo-review-form">${form}</div></div>` : form;
  openModal("New purchase", content, "PURCHASES");
  if (memoFile) {
    memoPreviewUrl = URL.createObjectURL(memoFile);
    $("#memo-preview-image").src = memoPreviewUrl;
    modal.classList.add("memo-review-modal");
  }
}
function saleForm() {
  if (!state.products.length) { notify("Add at least one product before making a sale.", true); return; }
  openModal("New sale", `<div class="sale-layout"><section class="sale-catalog"><div class="sale-section-head"><div><h3>Choose products</h3><p>Select items to add to the sale.</p></div></div><input id="sale-product-search" type="search" placeholder="Search products or SKU" aria-label="Search products"><div class="sale-product-grid">${state.products.map(saleProductCard).join("")}</div></section><form id="sale-form" class="sale-cart"><label>Customer<select name="customer_id" required>${customerOptions()}</select></label><button type="button" class="text-button sale-customer-toggle" data-action="toggle-sale-customer" aria-expanded="false" aria-controls="sale-new-customer">+ Add customer</button><div id="sale-new-customer" class="sale-new-customer" hidden><label>Customer name<input id="sale-customer-name" maxlength="150" autocomplete="name"></label><label>Phone <small>Optional</small><input id="sale-customer-phone" type="tel" maxlength="40" autocomplete="tel"></label><button type="button" class="btn small" data-action="save-sale-customer">Add and select customer</button></div><div class="sale-cart-heading"><h3>Sale items</h3><p>Adjust quantities before saving.</p></div><div id="sale-lines"></div><p id="sale-empty" class="sale-empty">Select a product to add it here.</p><div class="sale-summary"><div><span>Total</span><strong id="sale-total">${money(0)}</strong></div><div><span>Paid</span><strong id="sale-paid">${money(0)}</strong></div><div class="sale-due"><span>Due</span><strong id="sale-due">${money(0)}</strong></div></div><label>Amount paid now ৳<input name="initial_payment" type="number" min="0" max="0" step="0.01" value="0" required></label><p class="sale-note">Prices and stock are confirmed when the invoice is saved.</p>${actions("Complete sale")}</form></div>`, "SALES");
  modal.classList.add("sale-modal");
}
function pendingKey(type, body) {
  const storageKey = `oleyn.pending.${state.user.business_id}.${state.user.user_id}.${type}`;
  const signature = JSON.stringify(body); let previous;
  try { previous = JSON.parse(sessionStorage.getItem(storageKey) || "null"); } catch { previous = null; }
  const entry = previous?.signature === signature ? previous : {signature, key:crypto.randomUUID()};
  sessionStorage.setItem(storageKey, JSON.stringify(entry));
  return {key:entry.key, clear:() => sessionStorage.removeItem(storageKey)};
}
function readLines(form) {
  const rows = $$(".line-row", form);
  if (!rows.length) throw new Error("Add at least one item.");
  const ids = rows.map(row => Number($("[name=product_id]", row).value));
  if (new Set(ids).size !== ids.length) throw new Error("Each product can appear only once.");
  return rows.map(row => ({product_id:Number($("[name=product_id]",row).value), quantity:Number($("[name=quantity]",row).value), ...($("[name=unit_price]",row) ? {unit_price:$("[name=unit_price]",row).value} : {})}));
}
async function submitForm(form) {
  const values = formObject(form); const id = form.id;
  if (id === "login-form") { const user = await api("/auth/login", {method:"POST", json:values}); form.reset(); await startWorkspace(user); return; }
  if (id === "register-form") { await api("/auth/register", {method:"POST", json:values}); $("#login-form [name=email]").value = values.email; $("#login-form [name=business_name]").value = values.business_name; form.reset(); showAuth("login"); notify("Business created. Sign in to continue."); return; }
  if (id === "product-form") {
    const image = $("[name=image]", form).files[0];
    if (image && (!['image/jpeg', 'image/png'].includes(image.type) || image.size > 2 * 1024 * 1024)) throw new Error("Choose a JPEG or PNG image up to 2 MB.");
    const data = {name:values.name, selling_price:values.selling_price, purchase_cost:values.purchase_cost || null};
    if (values.sku) data.sku = values.sku; if (!form.dataset.id) data.opening_stock = Number(values.opening_stock);
    const product = await api(form.dataset.id ? `/products/${form.dataset.id}` : "/products", {method:form.dataset.id ? "PATCH" : "POST", json:data});
    if (image) {
      const body = new FormData(); body.append("file", image);
      try { await api(`/products/${product.product_id}/image`, {method:"PUT", body}); }
      catch (error) { closeModal(); await navigate(state.page); notify(`Product saved, but image upload failed: ${error.message} Edit the product to try again.`, true); return; }
    }
    notify("Product saved.");
  } else if (id === "adjust-form") { await api(`/products/${form.dataset.id}/adjustments`, {method:"POST", json:{quantity_change:Number(values.quantity_change), reason:values.reason}}); notify("Stock adjusted.");
  } else if (id === "customer-form") { await api("/customers", {method:"POST", json:{name:values.name, phone:values.phone || null}}); notify("Customer added.");
  } else if (id === "employee-form") { await api("/employees", {method:"POST", json:values}); notify("Salesperson added.");
  } else if (id === "purchase-form") {
    const data = {supplier_name:values.supplier_name || null, items:readLines(form)}; const pending = pendingKey("purchase",data);
    await api("/purchases", {method:"POST", json:data, headers:{"Idempotency-Key":pending.key}}); pending.clear(); notify("Purchase saved and stock updated.");
  } else if (id === "sale-form") {
    const data = {customer_id:Number(values.customer_id), items:readLines(form), initial_payment:values.initial_payment}; const pending = pendingKey("sale",data);
    const invoice = await api("/sales", {method:"POST", json:data, headers:{"Idempotency-Key":pending.key}}); pending.clear(); closeModal(); notify(`Invoice ${reference("INV", invoice.invoice_id)} saved.`); await navigate("sales"); return;
  } else if (id === "payment-form") {
    const data = {amount:values.amount}; const pending = pendingKey(`payment.${form.dataset.id}`,data);
    await api(`/sales/${form.dataset.id}/payments`, {method:"POST", json:data, headers:{"Idempotency-Key":pending.key}}); pending.clear(); notify("Payment recorded.");
  } else if (id === "memo-form") {
    const file = $("[name=file]",form).files[0]; if (!file) throw new Error("Choose a memo image.");
    const body = new FormData(); body.append("file",file); const draft = await api("/purchases/memo-draft", {method:"POST", body});
    if (modal.open && form.isConnected) purchaseForm(draft, file); return;
  }
  closeModal(); await navigate(state.page);
}
document.addEventListener("submit", async event => {
  const form = event.target; event.preventDefault(); const submit = $("button[type=submit]", form); if (submit) submit.disabled = true;
  const progress = form.id === "memo-form" ? $("#memo-progress", form) : null;
  const label = submit?.textContent; if (progress) progress.hidden = false; if (progress && submit) submit.textContent = "Reading memo…";
  try { await submitForm(form); } catch (error) { notify(error.message, true); } finally { if (submit) { submit.disabled = false; submit.textContent = label; } if (progress) progress.hidden = true; }
});
document.addEventListener("click", async event => {
  const target = event.target.closest("button"); if (!target) return;
  if (target.dataset.auth) { showAuth(target.dataset.auth); return; }
  if (target.dataset.page) { await navigate(target.dataset.page); return; }
  const action = target.dataset.action; if (!action) return;
  try {
    const id = Number(target.dataset.id);
    if (action === "close") closeModal();
    else if (action === "refresh") await navigate(state.page);
    else if (action === "new-product") productForm();
    else if (action === "edit-product") productForm(state.products.find(p => p.product_id === id));
    else if (action === "history") { const p = state.products.find(p => p.product_id === id); const rows = await api(`/products/${id}/history`); openModal(`${p.name} · stock history`, `<div class="history-list">${rows.length ? rows.map(r => `<div class="history-item"><strong>${r.quantity_change > 0 ? "+" : ""}${r.quantity_change} · ${esc(r.movement_type)}</strong>${r.reason ? ` · ${esc(movementReason(r))}` : ""}<small>${esc(r.created_at)} · User #${r.user_id}</small></div>`).join("") : `<p class="muted">No stock movements yet.</p>`}</div>`, "PRODUCTS & STOCK"); }
    else if (action === "adjust") { const p = state.products.find(p => p.product_id === id); openModal("Adjust stock", `<p class="muted">${esc(p.name)} currently has ${p.stock_quantity} units.</p><p class="info warning">If your connection fails, check stock history before retrying an adjustment.</p><form id="adjust-form" data-id="${id}" class="form-stack"><label>Change in quantity <small>Use a negative number to reduce stock.</small><input name="quantity_change" type="number" step="1" required></label><label>Reason<input name="reason" maxlength="255" required></label>${actions("Save adjustment")}</form>`, "PRODUCTS & STOCK"); }
    else if (action === "new-customer") openModal("Add customer", `<form id="customer-form" class="form-stack"><label>Customer name<input name="name" maxlength="150" required></label><label>Phone <small>Optional</small><input name="phone" type="tel" maxlength="40"></label>${actions("Add customer")}</form>`, "CUSTOMERS");
    else if (action === "new-employee") openModal("Add salesperson", `<p class="muted">Set the credentials your salesperson will use to sign in.</p><form id="employee-form" class="form-stack"><label>Name<input name="name" maxlength="150" required></label><label>Email<input name="email" type="email" required></label><label>Password<input name="password" type="password" minlength="8" maxlength="128" required><small>Share it privately. Password changes are not available yet.</small></label>${actions("Add salesperson")}</form>`, "TEAM");
    else if (action === "deactivate") { if (confirm("Deactivate this salesperson’s access?")) { await api(`/employees/${id}/deactivate`, {method:"PATCH"}); notify("Salesperson deactivated."); await navigate("employees"); } }
    else if (action === "new-purchase") purchaseForm();
    else if (action === "new-sale") saleForm();
    else if (action === "toggle-sale-customer") {
      const panel = $("#sale-new-customer"); panel.hidden = !panel.hidden;
      target.setAttribute("aria-expanded", String(!panel.hidden));
      if (!panel.hidden) $("#sale-customer-name").focus();
    }
    else if (action === "save-sale-customer") {
      const form = target.closest("#sale-form");
      const name = $("#sale-customer-name", form).value.trim();
      const phone = $("#sale-customer-phone", form).value.trim();
      if (!name) { notify("Enter the customer's name.", true); $("#sale-customer-name", form).focus(); return; }
      target.disabled = true;
      try {
        const customer = await api("/customers", {method:"POST", json:{name, phone:phone || null}});
        state.customers.push(customer);
        if (form.isConnected) {
          const select = $("[name=customer_id]", form); const option = document.createElement("option");
          option.value = customer.customer_id; option.textContent = customer.name; select.append(option); select.value = String(customer.customer_id);
          $("#sale-customer-name", form).value = ""; $("#sale-customer-phone", form).value = "";
          $("#sale-new-customer", form).hidden = true; $("[data-action=toggle-sale-customer]", form).setAttribute("aria-expanded", "false");
          notify("Customer added and selected.");
        }
      } finally { target.disabled = false; }
    }
    else if (action === "add-purchase-line") $("#purchase-lines").insertAdjacentHTML("beforeend", purchaseRow());
    else if (action === "add-sale-product") addSaleProduct(id);
    else if (action === "remove-sale-line") { target.closest(".sale-cart-line").remove(); updateSaleTotals(); }
    else if (action === "remove-line") target.closest(".line-row").remove();
    else if (action === "payment") { const invoice = state.sales.find(s => s.invoice_id === id); openModal("Record a payment", `<p class="muted">Invoice ${reference("INV", id)} · ${esc(invoice.customer_name)}</p><p class="info">Outstanding due: <strong>${money(invoice.due)}</strong></p><form id="payment-form" data-id="${id}" class="form-stack"><label>Amount received ৳<input name="amount" type="number" min="0.01" max="${esc(invoice.due)}" step="0.01" required></label>${actions("Record payment")}</form>`, "CUSTOMER DUES"); }
    else if (action === "memo") openModal("Scan a purchase memo", `<p class="muted">Upload a clear photo of a supplier memo. You’ll review the draft before anything is saved.</p><p class="info">The photo is sent to Google for extraction. Use JPEG or PNG, up to 5 MB. If scanning fails, enter the purchase manually.</p><form id="memo-form" class="form-stack"><label>Memo photo<input name="file" type="file" accept="image/png,image/jpeg" required></label><p id="memo-progress" class="info" role="status" aria-live="polite" hidden>Reading your memo. This can take a little while; please wait.</p>${actions("Read memo")}</form>`, "PURCHASES");
  } catch (error) { notify(error.message, true); }
});
document.addEventListener("input", event => {
  if (event.target.id === "sale-product-search") {
    const query = event.target.value.toLowerCase().trim();
    $$(".sale-product").forEach(card => { card.hidden = !card.dataset.search.includes(query); });
    return;
  }
  if (event.target.closest("#sale-form") && (event.target.name === "quantity" || event.target.name === "initial_payment")) { updateSaleTotals(); return; }
  if (event.target.id !== "product-search") return;
  const query = event.target.value.toLowerCase().trim();
  $$("#product-table tbody tr").forEach(row => {row.hidden = !row.textContent.toLowerCase().includes(query);});
});
document.addEventListener("keydown", event => {
  if (event.key === "Enter" && event.target.closest("#sale-new-customer")) {
    event.preventDefault(); $("[data-action=save-sale-customer]", event.target.closest("#sale-form")).click();
  }
});
$("#modal-close").addEventListener("click", closeModal);
for (const button of [$("#logout"), $("#logout-top")]) button.addEventListener("click", async () => { try { await api("/auth/logout",{method:"POST"}); state.user = null; showAuth(); } catch (error) { notify(error.message,true); } });
api("/auth/me").then(startWorkspace).catch(() => showAuth());
