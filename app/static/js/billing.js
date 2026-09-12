/**
 * Billing Form Dynamic Rows
 * Production-grade vanilla JS with autocomplete support
 */
(function() {
  const addBtn = document.getElementById('addRowBtn');
  const rowsContainer = document.getElementById('productRows');

  if (!addBtn || !rowsContainer) return;

  function createRow() {
    const div = document.createElement('div');
    div.className = 'product-row';
    div.innerHTML = `
      <div class="form-group">
        <label>Product ID</label>
        <input type="text" name="product_id" list="productList" placeholder="e.g. P101" required>
      </div>
      <div class="form-group">
        <label>Quantity</label>
        <input type="number" name="quantity" min="1" value="1" required>
      </div>
      <button type="button" class="btn btn-danger btn-sm remove-row" onclick="removeRow(this)">Remove</button>
    `;
    return div;
  }

  addBtn.addEventListener('click', function() {
    const newRow = createRow();
    rowsContainer.appendChild(newRow);
    // Focus new input
    const input = newRow.querySelector('input[name="product_id"]');
    if (input) input.focus();
  });

  window.removeRow = function(btn) {
    const row = btn.closest('.product-row');
    const allRows = rowsContainer.querySelectorAll('.product-row');
    // Keep at least one row
    if (allRows.length <= 1) {
      alert('At least one product row is required.');
      return;
    }
    row.remove();
  };

  // Form validation before submit
  const form = document.getElementById('billingForm');
  if (form) {
    form.addEventListener('submit', function(e) {
      const email = document.getElementById('customer_email');
      const cash = document.getElementById('cash_paid');
      const productIds = form.querySelectorAll('input[name="product_id"]');

      let hasValidProduct = false;
      productIds.forEach(inp => {
        if (inp.value.trim() !== '') hasValidProduct = true;
      });

      if (!hasValidProduct) {
        e.preventDefault();
        alert('Please add at least one product.');
        return false;
      }

      // Disable button to prevent double submit
      const submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Generating...';
        setTimeout(() => { submitBtn.disabled = false; submitBtn.textContent = 'Generate Bill'; }, 3000);
      }
    });

    // Reset handler - ensure at least one row remains
    form.addEventListener('reset', function() {
      setTimeout(() => {
        const rows = rowsContainer.querySelectorAll('.product-row');
        // If reset cleared rows, ensure one exists
        if (rows.length === 0) {
          rowsContainer.appendChild(createRow());
        } else if (rows.length > 1) {
          // Keep only first row on reset? No, remove extra
          // But native reset keeps values - we want clean
          // So keep first and remove rest
          for (let i = 1; i < rows.length; i++) rows[i].remove();
          // Reset first row values
          const first = rows[0];
          first.querySelector('input[name="product_id"]').value = '';
          first.querySelector('input[name="quantity"]').value = '1';
        }
      }, 50);
    });
  }

  // Auto-uppercase product ID
  document.addEventListener('input', function(e) {
    if (e.target.name === 'product_id') {
      // Uppercase but keep cursor
      const start = e.target.selectionStart;
      const end = e.target.selectionEnd;
      e.target.value = e.target.value.toUpperCase();
      e.target.setSelectionRange(start, end);
    }
  });
})();
