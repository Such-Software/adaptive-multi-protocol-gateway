(function () {
  const filters = Array.from(document.querySelectorAll("[data-filter]"));
  const products = Array.from(document.querySelectorAll("[data-category]"));
  const estimate = document.getElementById("estimate");

  if (filters.length === 0 || products.length === 0) {
    return;
  }

  function setFilter(category) {
    filters.forEach((button) => {
      const selected = button.dataset.filter === category;
      button.classList.toggle("active", selected);
      button.setAttribute("aria-pressed", selected ? "true" : "false");
    });

    let total = 0;
    let count = 0;
    products.forEach((product) => {
      const visible = category === "all" || product.dataset.category === category;
      product.hidden = !visible;
      if (visible) {
        count += 1;
        total += Number(product.dataset.price || 0);
      }
    });

    if (estimate) {
      estimate.textContent =
        count === products.length
          ? `All ${count} kits total $${total}.`
          : `${count} matching kits total $${total}.`;
    }
  }

  filters.forEach((button) => {
    button.addEventListener("click", () => setFilter(button.dataset.filter || "all"));
  });

  setFilter("all");
})();
