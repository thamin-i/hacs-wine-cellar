class WineCellarCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._data = { bottles: [], locations: [], history: [], settings: {}, stats: {} };
    this._tab = "inventory";
    this._loading = false;
    this._message = "";
    this._search = "";
    this._typeFilter = "all";
    this._sort = "name";
    this._formOpen = false;
    this._editingId = "";
    this._form = this._emptyBottle();
    this._pendingImage = "";
    this._pendingImageName = "";
    this._locationForm = { name: "", location_type: "rack", capacity: 0, notes: "" };
    this._restoreBackups = [];
  }

  setConfig(config) {
    this._config = config || {};
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._loaded && hass) {
      this._loadData();
    }
  }

  connectedCallback() {
    this._render();
    if (this._hass && !this._loaded) {
      this._loadData();
    }
  }

  static getStubConfig() {
    return { type: "custom:wine-cellar-card", title: "Wine Cellar" };
  }

  async _loadData() {
    if (!this._hass) return;
    this._loading = true;
    this._render();
    try {
      this._data = await this._hass.callWS({ type: "wine_cellar/get_data" });
      this._loaded = true;
    } catch (err) {
      this._message = `Failed to load wine cellar: ${err.message || err}`;
    }
    this._loading = false;
    this._render();
  }

  _emptyBottle() {
    return {
      name: "",
      producer: "",
      vintage: "",
      wine_type: "red",
      country: "",
      region: "",
      appellation: "",
      grapes: "",
      bottle_size: "750ml",
      purchase_price: "",
      estimated_value: "",
      purchase_date: "",
      drink_from: "",
      drink_by: "",
      rating: "",
      notes: "",
      tags: "",
      barcode: "",
      location_id: "",
    };
  }

  _render() {
    if (!this.shadowRoot) return;
    const title = this._config.title || "Wine Cellar";
    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <ha-card>
        <div class="header">
          <div>
            <h2>${this._escape(title)}</h2>
            <div class="sub">${this._summaryText()}</div>
          </div>
          <button class="primary" data-action="new-bottle">Add Bottle</button>
        </div>
        ${this._message ? `<div class="message">${this._escape(this._message)}</div>` : ""}
        <div class="tabs">
          ${this._tabButton("inventory", "Inventory")}
          ${this._tabButton("locations", "Locations")}
          ${this._tabButton("ready", "Ready To Drink")}
          ${this._tabButton("history", "History")}
          ${this._tabButton("stats", "Stats")}
          ${this._tabButton("settings", "Settings")}
        </div>
        <div class="body">
          ${this._loading ? `<div class="loading">Loading...</div>` : this._renderTab()}
        </div>
        ${this._formOpen ? this._renderBottleForm() : ""}
      </ha-card>
    `;
    this._wireEvents();
  }

  _tabButton(id, label) {
    return `<button class="${this._tab === id ? "active" : ""}" data-tab="${id}">${label}</button>`;
  }

  _renderTab() {
    if (this._tab === "locations") return this._renderLocations();
    if (this._tab === "ready") return this._renderReady();
    if (this._tab === "history") return this._renderHistory();
    if (this._tab === "stats") return this._renderStats();
    if (this._tab === "settings") return this._renderSettings();
    return this._renderInventory();
  }

  _renderInventory(customBottles) {
    const bottles = customBottles || this._filteredBottles();
    return `
      <div class="toolbar">
        <input class="search" placeholder="Search bottles..." value="${this._escapeAttr(this._search)}" />
        <select class="type-filter">
          ${["all", "red", "white", "rosé", "sparkling", "dessert", "fortified", "other"].map((type) => `
            <option value="${type}" ${this._typeFilter === type ? "selected" : ""}>${this._label(type)}</option>
          `).join("")}
        </select>
        <select class="sort">
          ${[
            ["name", "Name"],
            ["vintage", "Vintage"],
            ["drink_by", "Drink By"],
            ["estimated_value", "Value"],
            ["created_at", "Added"],
          ].map(([value, label]) => `<option value="${value}" ${this._sort === value ? "selected" : ""}>${label}</option>`).join("")}
        </select>
      </div>
      <div class="list">
        ${bottles.length ? bottles.map((bottle) => this._renderBottleItem(bottle)).join("") : `<div class="empty">No bottles yet.</div>`}
      </div>
    `;
  }

  _renderBottleItem(bottle) {
    const location = this._locationName(bottle.location_id);
    const value = bottle.estimated_value ?? bottle.purchase_price;
    return `
      <div class="bottle">
        <div class="thumb">${bottle.image_url ? `<img src="${this._escapeAttr(bottle.image_url)}" alt="">` : `<span>${this._typeInitial(bottle.wine_type)}</span>`}</div>
        <div class="bottle-main">
          <div class="bottle-title">${this._escape(bottle.name)}</div>
          <div class="muted">${this._escape([bottle.producer, bottle.vintage, bottle.region].filter(Boolean).join(" · "))}</div>
          <div class="chips">
            <span>${this._label(bottle.wine_type)}</span>
            ${location ? `<span>${this._escape(location)}</span>` : `<span>Unassigned</span>`}
            ${bottle.drink_by ? `<span>Drink by ${this._escape(bottle.drink_by)}</span>` : ""}
          </div>
        </div>
        <div class="bottle-side">
          ${value ? `<div class="value">${this._money(value)}</div>` : ""}
          <div class="actions">
            <button data-action="edit-bottle" data-id="${bottle.id}">Edit</button>
            <button data-action="duplicate-bottle" data-id="${bottle.id}">Duplicate</button>
            <button data-action="drink-bottle" data-id="${bottle.id}">Drank</button>
            <button class="danger" data-action="remove-bottle" data-id="${bottle.id}">Remove</button>
          </div>
        </div>
      </div>
    `;
  }

  _renderReady() {
    const year = new Date().getFullYear();
    const ready = this._data.bottles.filter((bottle) => {
      const from = Number(bottle.drink_from || 0);
      const by = Number(bottle.drink_by || 0);
      return (from || by) && (!from || from <= year) && (!by || by >= year);
    });
    return this._renderInventory(ready);
  }

  _renderLocations() {
    const locations = this._data.locations || [];
    return `
      <div class="locations">
        <form class="location-form">
          <input name="name" placeholder="Location name" value="${this._escapeAttr(this._locationForm.name)}" required>
          <select name="location_type">
            ${["rack", "fridge", "shelf", "box", "cabinet", "offsite", "other"].map((type) => `<option value="${type}" ${this._locationForm.location_type === type ? "selected" : ""}>${this._label(type)}</option>`).join("")}
          </select>
          <input name="capacity" type="number" min="0" placeholder="Capacity" value="${this._escapeAttr(this._locationForm.capacity)}">
          <input name="notes" placeholder="Notes" value="${this._escapeAttr(this._locationForm.notes)}">
          <button class="primary">Add Location</button>
        </form>
        <div class="list">
          ${locations.length ? locations.map((location) => this._renderLocationItem(location)).join("") : `<div class="empty">No locations yet.</div>`}
        </div>
      </div>
    `;
  }

  _renderLocationItem(location) {
    const count = this._data.bottles.filter((bottle) => bottle.location_id === location.id).length;
    const capacity = Number(location.capacity || 0);
    return `
      <div class="location">
        <div>
          <div class="bottle-title">${this._escape(location.name)}</div>
          <div class="muted">${this._label(location.location_type)} · ${count}/${capacity || "∞"} bottles</div>
          ${location.notes ? `<div class="notes">${this._escape(location.notes)}</div>` : ""}
        </div>
        <div class="actions">
          <button data-action="edit-location" data-id="${location.id}">Edit</button>
          <button class="danger" data-action="remove-location" data-id="${location.id}">Remove</button>
        </div>
      </div>
    `;
  }

  _renderHistory() {
    const history = this._data.history || [];
    return `
      <div class="list">
        ${history.length ? history.map((entry) => {
          const bottle = entry.bottle || {};
          return `
            <div class="bottle">
              <div class="thumb">${bottle.image_url ? `<img src="${this._escapeAttr(bottle.image_url)}" alt="">` : `<span>${this._typeInitial(bottle.wine_type)}</span>`}</div>
              <div class="bottle-main">
                <div class="bottle-title">${this._escape(bottle.name || "Removed bottle")}</div>
                <div class="muted">${this._escape([bottle.producer, bottle.vintage, entry.reason, this._date(entry.removed_at)].filter(Boolean).join(" · "))}</div>
                ${entry.notes ? `<div class="notes">${this._escape(entry.notes)}</div>` : ""}
              </div>
              <button data-action="restore-history" data-id="${entry.id}">Restore</button>
            </div>
          `;
        }).join("") : `<div class="empty">No removed bottles yet.</div>`}
      </div>
    `;
  }

  _renderStats() {
    const stats = this._data.stats || {};
    const byType = stats.by_type || {};
    return `
      <div class="stats">
        ${this._stat("Total Bottles", stats.total_bottles)}
        ${this._stat("Total Value", this._money(stats.total_value || 0))}
        ${this._stat("Ready To Drink", stats.ready_to_drink)}
        ${this._stat("Past Peak", stats.past_peak)}
        ${this._stat("Capacity Used", `${stats.capacity_used || 0}%`)}
        ${this._stat("Unassigned", stats.unassigned_bottles)}
      </div>
      <h3>By Type</h3>
      <div class="chips big">
        ${Object.keys(byType).length ? Object.entries(byType).map(([type, count]) => `<span>${this._label(type)}: ${count}</span>`).join("") : `<span>No data</span>`}
      </div>
    `;
  }

  _renderSettings() {
    return `
      <div class="settings">
        <h3>Backups</h3>
        <div class="button-row">
          <button data-action="download-backup">Download Full JSON Backup</button>
          <button data-action="server-backup">Save Server Backup</button>
          <button data-action="list-backups">Show Server Backups</button>
          <label class="file-button">Restore JSON<input type="file" class="restore-json" accept="application/json"></label>
        </div>
        ${this._restoreBackups.length ? `<div class="backup-list">${this._restoreBackups.map((backup) => `
          <div class="location">
            <div>
              <div class="bottle-title">${this._escape(backup.filename)}</div>
              <div class="muted">${backup.bottles || 0} bottles · ${backup.media || 0} photos · ${this._date(backup.created_at)}</div>
            </div>
            <button data-action="restore-server" data-filename="${this._escapeAttr(backup.filename)}">Restore</button>
          </div>
        `).join("")}</div>` : ""}

        <h3>CSV Metadata</h3>
        <div class="button-row">
          <button data-action="download-csv">Download CSV</button>
          <label class="file-button">Import CSV<input type="file" class="import-csv" accept=".csv,text/csv"></label>
        </div>
        <p class="muted">CSV import/export includes metadata only. Use full JSON backup for photos.</p>
      </div>
    `;
  }

  _stat(label, value) {
    return `<div class="stat"><div class="stat-value">${this._escape(value ?? 0)}</div><div class="muted">${this._escape(label)}</div></div>`;
  }

  _renderBottleForm() {
    const f = this._form;
    const title = this._editingId ? "Edit Bottle" : "Add Bottle";
    const preview = this._pendingImage || f.image_url || "";
    return `
      <div class="modal-backdrop">
        <form class="modal bottle-form">
          <div class="modal-head">
            <h3>${title}</h3>
            <button type="button" data-action="close-form">Close</button>
          </div>
          <div class="photo-row">
            <div class="photo-preview">${preview ? `<img src="${this._escapeAttr(preview)}" alt="">` : `<span>No photo</span>`}</div>
            <div>
              <label class="file-button">Take or Upload Photo<input type="file" class="photo-input" accept="image/*" capture="environment"></label>
              ${f.image_id || this._pendingImage ? `<button type="button" data-action="delete-photo">Delete Photo</button>` : ""}
            </div>
          </div>
          <div class="grid">
            ${this._input("name", "Name", true)}
            ${this._input("producer", "Producer")}
            ${this._input("vintage", "Vintage", false, "number")}
            ${this._select("wine_type", "Type", ["red", "white", "rosé", "sparkling", "dessert", "fortified", "other"])}
            ${this._input("country", "Country")}
            ${this._input("region", "Region")}
            ${this._input("appellation", "Appellation")}
            ${this._input("grapes", "Grapes")}
            ${this._input("bottle_size", "Bottle Size")}
            ${this._input("purchase_price", "Purchase Price", false, "number", "0.01")}
            ${this._input("estimated_value", "Estimated Value", false, "number", "0.01")}
            ${this._input("purchase_date", "Purchase Date", false, "date")}
            ${this._input("drink_from", "Drink From", false, "number")}
            ${this._input("drink_by", "Drink By", false, "number")}
            ${this._input("rating", "Rating 0-5", false, "number", "0.5")}
            ${this._input("barcode", "Barcode")}
            ${this._locationSelect()}
            ${this._input("tags", "Tags")}
          </div>
          <label class="full">Notes<textarea name="notes">${this._escape(f.notes || "")}</textarea></label>
          <div class="button-row end">
            <button type="button" data-action="close-form">Cancel</button>
            <button class="primary">Save Bottle</button>
          </div>
        </form>
      </div>
    `;
  }

  _input(name, label, required = false, type = "text", step = "") {
    return `
      <label>${label}
        <input name="${name}" type="${type}" ${required ? "required" : ""} ${step ? `step="${step}"` : ""} value="${this._escapeAttr(this._form[name] ?? "")}">
      </label>
    `;
  }

  _select(name, label, values) {
    return `
      <label>${label}
        <select name="${name}">
          ${values.map((value) => `<option value="${value}" ${this._form[name] === value ? "selected" : ""}>${this._label(value)}</option>`).join("")}
        </select>
      </label>
    `;
  }

  _locationSelect() {
    return `
      <label>Location
        <select name="location_id">
          <option value="">Unassigned</option>
          ${(this._data.locations || []).map((location) => `<option value="${location.id}" ${this._form.location_id === location.id ? "selected" : ""}>${this._escape(location.name)}</option>`).join("")}
        </select>
      </label>
    `;
  }

  _wireEvents() {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-tab]").forEach((button) => {
      button.addEventListener("click", () => {
        this._tab = button.dataset.tab;
        this._render();
      });
    });
    root.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", (event) => this._handleAction(event));
    });
    root.querySelector(".search")?.addEventListener("input", (event) => {
      this._search = event.target.value;
      this._render();
    });
    root.querySelector(".type-filter")?.addEventListener("change", (event) => {
      this._typeFilter = event.target.value;
      this._render();
    });
    root.querySelector(".sort")?.addEventListener("change", (event) => {
      this._sort = event.target.value;
      this._render();
    });
    root.querySelector(".bottle-form")?.addEventListener("submit", (event) => this._saveBottle(event));
    root.querySelector(".photo-input")?.addEventListener("change", (event) => this._handlePhoto(event));
    root.querySelector(".location-form")?.addEventListener("submit", (event) => this._addLocation(event));
    root.querySelector(".restore-json")?.addEventListener("change", (event) => this._restoreJson(event));
    root.querySelector(".import-csv")?.addEventListener("change", (event) => this._importCsv(event));
  }

  async _handleAction(event) {
    const action = event.currentTarget.dataset.action;
    const id = event.currentTarget.dataset.id;
    const filename = event.currentTarget.dataset.filename;
    if (action === "new-bottle") this._openBottleForm();
    if (action === "close-form") this._closeForm();
    if (action === "edit-bottle") this._openBottleForm(this._data.bottles.find((b) => b.id === id));
    if (action === "duplicate-bottle") await this._call({ type: "wine_cellar/duplicate_bottle", bottle_id: id }, "Bottle duplicated");
    if (action === "drink-bottle") await this._removeBottle(id, "drank");
    if (action === "remove-bottle") await this._removeBottle(id, "other");
    if (action === "restore-history") await this._call({ type: "wine_cellar/restore_history", history_id: id }, "Bottle restored");
    if (action === "edit-location") await this._editLocation(id);
    if (action === "remove-location") await this._removeLocation(id);
    if (action === "delete-photo") await this._deletePhoto();
    if (action === "download-backup") await this._downloadBackup();
    if (action === "server-backup") await this._call({ type: "wine_cellar/server_backup_save" }, "Server backup saved", false);
    if (action === "list-backups") await this._listBackups();
    if (action === "restore-server") {
      if (!confirm("Restore this backup? Current cellar data will be replaced.")) return;
      await this._call({ type: "wine_cellar/server_backup_restore", filename }, "Server backup restored");
    }
    if (action === "download-csv") await this._downloadCsv();
  }

  _openBottleForm(bottle = null) {
    this._editingId = bottle?.id || "";
    this._form = bottle ? { ...this._emptyBottle(), ...bottle, tags: (bottle.tags || []).join(", ") } : this._emptyBottle();
    this._pendingImage = "";
    this._pendingImageName = "";
    this._formOpen = true;
    this._render();
  }

  _closeForm() {
    this._formOpen = false;
    this._editingId = "";
    this._pendingImage = "";
    this._pendingImageName = "";
    this._render();
  }

  async _saveBottle(event) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const bottle = {};
    for (const [key, value] of formData.entries()) {
      bottle[key] = value;
    }
    try {
      let result;
      if (this._editingId) {
        result = await this._hass.callWS({ type: "wine_cellar/update_bottle", bottle_id: this._editingId, updates: bottle });
      } else {
        result = await this._hass.callWS({ type: "wine_cellar/add_bottle", bottle });
      }
      if (result.error) throw new Error(result.error);
      const saved = result.bottle;
      if (this._pendingImage && saved?.id) {
        const photo = await this._hass.callWS({
          type: "wine_cellar/set_bottle_photo",
          bottle_id: saved.id,
          image: this._pendingImage,
          filename: this._pendingImageName,
        });
        if (photo.error) throw new Error(photo.error);
      }
      this._message = "Bottle saved";
      this._closeForm();
      await this._loadData();
    } catch (err) {
      this._message = `Failed to save bottle: ${err.message || err}`;
      this._render();
    }
  }

  async _handlePhoto(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      this._pendingImage = await this._resizeImage(file);
      this._pendingImageName = file.name || "bottle.jpg";
      this._render();
    } catch (err) {
      this._message = `Photo failed: ${err.message || err}`;
      this._render();
    }
  }

  async _deletePhoto() {
    if (this._pendingImage) {
      this._pendingImage = "";
      this._pendingImageName = "";
      this._render();
      return;
    }
    if (!this._editingId) return;
    await this._call({ type: "wine_cellar/delete_bottle_photo", bottle_id: this._editingId }, "Photo deleted");
    this._closeForm();
  }

  async _addLocation(event) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const location = Object.fromEntries(formData.entries());
    await this._call({ type: "wine_cellar/add_location", location }, "Location added");
    this._locationForm = { name: "", location_type: "rack", capacity: 0, notes: "" };
  }

  async _editLocation(id) {
    const location = this._data.locations.find((item) => item.id === id);
    if (!location) return;
    const name = prompt("Location name", location.name);
    if (name === null) return;
    const capacity = prompt("Capacity", location.capacity || 0);
    if (capacity === null) return;
    await this._call({
      type: "wine_cellar/update_location",
      location_id: id,
      updates: { name, capacity },
    }, "Location updated");
  }

  async _removeLocation(id) {
    if (!confirm("Remove this location? Bottles will become unassigned.")) return;
    await this._call({ type: "wine_cellar/remove_location", location_id: id }, "Location removed");
  }

  async _removeBottle(id, reason) {
    if (!confirm(reason === "drank" ? "Mark this bottle as drank?" : "Remove this bottle?")) return;
    await this._call({ type: "wine_cellar/remove_bottle", bottle_id: id, reason }, "Bottle removed");
  }

  async _downloadBackup() {
    const backup = await this._hass.callWS({ type: "wine_cellar/get_backup" });
    this._download(JSON.stringify(backup, null, 2), `wine_cellar_backup_${this._stamp()}.json`, "application/json");
  }

  async _restoreJson(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    const backup = JSON.parse(text);
    if (!confirm("Restore this backup? Current cellar data will be replaced.")) return;
    await this._call({ type: "wine_cellar/restore_backup", backup }, "Backup restored");
  }

  async _listBackups() {
    const result = await this._hass.callWS({ type: "wine_cellar/server_backup_list" });
    this._restoreBackups = result.backups || [];
    this._message = `${this._restoreBackups.length} server backup(s) found`;
    this._render();
  }

  async _downloadCsv() {
    const result = await this._hass.callWS({ type: "wine_cellar/export_csv" });
    this._download(result.csv || "", `wine_cellar_${this._stamp()}.csv`, "text/csv");
  }

  async _importCsv(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    const csv = await file.text();
    await this._call({ type: "wine_cellar/import_csv", csv }, "CSV imported");
  }

  async _call(payload, successMessage, reload = true) {
    try {
      const result = await this._hass.callWS(payload);
      if (result?.error) throw new Error(result.error);
      this._message = successMessage;
      if (reload) await this._loadData();
      else this._render();
      return result;
    } catch (err) {
      this._message = err.message || String(err);
      this._render();
      return null;
    }
  }

  _filteredBottles() {
    const query = this._search.trim().toLowerCase();
    let bottles = [...(this._data.bottles || [])];
    if (this._typeFilter !== "all") {
      bottles = bottles.filter((bottle) => bottle.wine_type === this._typeFilter);
    }
    if (query) {
      bottles = bottles.filter((bottle) => [
        bottle.name,
        bottle.producer,
        bottle.vintage,
        bottle.country,
        bottle.region,
        bottle.appellation,
        bottle.grapes,
        bottle.notes,
        (bottle.tags || []).join(" "),
        this._locationName(bottle.location_id),
      ].join(" ").toLowerCase().includes(query));
    }
    bottles.sort((a, b) => {
      const av = a[this._sort] || "";
      const bv = b[this._sort] || "";
      if (this._sort === "vintage" || this._sort === "drink_by" || this._sort === "estimated_value") {
        return Number(bv || 0) - Number(av || 0);
      }
      return String(av).localeCompare(String(bv));
    });
    return bottles;
  }

  _summaryText() {
    const stats = this._data.stats || {};
    return `${stats.total_bottles || 0} bottles · ${stats.ready_to_drink || 0} ready · ${this._money(stats.total_value || 0)}`;
  }

  _locationName(id) {
    return (this._data.locations || []).find((location) => location.id === id)?.name || "";
  }

  _typeInitial(type) {
    return (type || "w").slice(0, 1).toUpperCase();
  }

  _label(value) {
    return String(value || "").replace(/_/g, " ").replace(/\b\w/g, (match) => match.toUpperCase());
  }

  _money(value) {
    const currency = this._data.settings?.currency || "EUR";
    const number = Number(value || 0);
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(number);
  }

  _date(value) {
    if (!value) return "";
    try {
      return new Date(value).toLocaleDateString();
    } catch {
      return value;
    }
  }

  _stamp() {
    return new Date().toISOString().replace(/[:.]/g, "-");
  }

  _download(content, filename, type) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  _resizeImage(file) {
    return new Promise((resolve, reject) => {
      if (!file.type.startsWith("image/")) {
        reject(new Error("Choose an image file"));
        return;
      }
      const reader = new FileReader();
      reader.onerror = () => reject(new Error("Could not read image"));
      reader.onload = () => {
        const img = new Image();
        img.onerror = () => reject(new Error("Could not load image"));
        img.onload = () => {
          const max = 1400;
          let { width, height } = img;
          if (width > height && width > max) {
            height = Math.round((height * max) / width);
            width = max;
          } else if (height > max) {
            width = Math.round((width * max) / height);
            height = max;
          }
          const canvas = document.createElement("canvas");
          canvas.width = width;
          canvas.height = height;
          canvas.getContext("2d").drawImage(img, 0, 0, width, height);
          resolve(canvas.toDataURL("image/jpeg", 0.82));
        };
        img.src = reader.result;
      };
      reader.readAsDataURL(file);
    });
  }

  _escape(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[char]));
  }

  _escapeAttr(value) {
    return this._escape(value).replace(/`/g, "&#96;");
  }

  _styles() {
    return `
      :host { display: block; }
      ha-card { overflow: hidden; }
      .header { display: flex; justify-content: space-between; gap: 16px; align-items: center; padding: 16px; border-bottom: 1px solid var(--divider-color); }
      h2, h3 { margin: 0; }
      .sub, .muted { color: var(--secondary-text-color); font-size: 0.9rem; }
      .tabs { display: flex; overflow-x: auto; border-bottom: 1px solid var(--divider-color); }
      .tabs button { border: 0; background: transparent; color: var(--primary-text-color); padding: 12px 14px; cursor: pointer; white-space: nowrap; }
      .tabs button.active { color: var(--primary-color); box-shadow: inset 0 -2px 0 var(--primary-color); }
      .body { padding: 16px; }
      button, .file-button { border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); border-radius: 6px; padding: 8px 10px; cursor: pointer; font: inherit; display: inline-flex; align-items: center; justify-content: center; gap: 6px; }
      button.primary { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color); }
      button.danger { color: var(--error-color, #b00020); }
      input, select, textarea { width: 100%; box-sizing: border-box; border: 1px solid var(--divider-color); border-radius: 6px; padding: 9px; background: var(--card-background-color); color: var(--primary-text-color); font: inherit; }
      textarea { min-height: 90px; resize: vertical; }
      .toolbar, .button-row, .location-form { display: grid; grid-template-columns: minmax(160px, 1fr) auto auto auto; gap: 8px; align-items: center; margin-bottom: 14px; }
      .list { display: grid; gap: 10px; }
      .bottle, .location { display: flex; gap: 12px; align-items: center; border: 1px solid var(--divider-color); border-radius: 8px; padding: 10px; }
      .bottle-main { flex: 1; min-width: 0; }
      .bottle-title { font-weight: 650; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .bottle-side { display: grid; justify-items: end; gap: 8px; }
      .actions { display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-end; }
      .thumb, .photo-preview { width: 64px; height: 84px; border-radius: 6px; background: rgba(127,127,127,.12); display: grid; place-items: center; overflow: hidden; flex: 0 0 auto; font-weight: 700; }
      .thumb img, .photo-preview img { width: 100%; height: 100%; object-fit: cover; }
      .photo-preview { width: 110px; height: 140px; }
      .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
      .chips span { border: 1px solid var(--divider-color); border-radius: 999px; padding: 3px 8px; font-size: 0.78rem; color: var(--secondary-text-color); }
      .chips.big span { font-size: 0.9rem; }
      .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 18px; }
      .stat { border: 1px solid var(--divider-color); border-radius: 8px; padding: 12px; }
      .stat-value { font-size: 1.4rem; font-weight: 700; }
      .message { margin: 12px 16px 0; padding: 10px; border-radius: 6px; background: rgba(127,127,127,.12); }
      .empty, .loading { padding: 28px; text-align: center; color: var(--secondary-text-color); }
      .modal-backdrop { position: fixed; inset: 0; z-index: 1000; background: rgba(0,0,0,.45); display: grid; place-items: center; padding: 16px; }
      .modal { max-width: 760px; width: 100%; max-height: 92vh; overflow: auto; background: var(--card-background-color); color: var(--primary-text-color); border-radius: 8px; padding: 16px; box-shadow: var(--ha-card-box-shadow); }
      .modal-head, .photo-row { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 16px; }
      .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; }
      label { display: grid; gap: 4px; font-size: 0.88rem; }
      label.full { margin-top: 10px; }
      .file-button { position: relative; overflow: hidden; }
      .file-button input { position: absolute; opacity: 0; inset: 0; cursor: pointer; }
      .end { justify-content: end; grid-template-columns: auto auto; margin-top: 14px; }
      .settings h3 { margin: 16px 0 8px; }
      .notes { margin-top: 5px; color: var(--secondary-text-color); }
      @media (max-width: 700px) {
        .header, .bottle, .location, .photo-row { align-items: stretch; flex-direction: column; }
        .toolbar, .button-row, .location-form { grid-template-columns: 1fr; }
        .bottle-side { justify-items: start; }
        .actions { justify-content: flex-start; }
      }
    `;
  }
}

customElements.define("wine-cellar-card", WineCellarCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "wine-cellar-card",
  name: "Wine Cellar",
  description: "Local-only wine cellar inventory",
});
