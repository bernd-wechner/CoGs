// Taken from: https://jsfiddle.net/schinckel/gge7v234/

function isChecked(element) {
  return element.checked;
}

function getValue(element) {
  return element.value;
}

function WeekdayWidget(element) {
  var parts = Array.apply(null, element.querySelectorAll('.week-parts [type=checkbox]'));
  var days = Array.apply(null, element.querySelectorAll('.days [type=checkbox]'));

  function value() {
    return days.filter(isChecked).map(getValue);
  }

  this.value = value;

  function updateParts(selected) {

    function notSelected(val) {
      return selected.indexOf(val) === -1;
    }

    parts.forEach(function(part) {
      var partDays = part.dataset.values.split(',');
      var notSelectedParts = partDays.filter(notSelected);
      if (notSelectedParts.length === 0) {
        part.checked = true;
        part.indeterminate = false;
      } else if (notSelectedParts.length === partDays.length) {
        part.checked = false;
        part.indeterminate = false;
      } else {
        part.indeterminate = true;
      }
      // if (partDays.length === partDays.filter(notSelected).length)
      // part.checked = partDays.filter(notSelected).length === 0;
    });
  }

  function updateDays(values, checked) {
    days.forEach(function(ele) {
      if (values.indexOf(ele.value) > -1) {
        ele.checked = checked;
      }
    });
  }

  element.addEventListener('change', function(event) {
    if (event.target.tagName === 'INPUT') {
      if (event.target.name === element.dataset.name) {
        updateParts(value());
      } else {
        updateDays(event.target.dataset.values.split(','), event.target.checked);
        updateParts(value());
      }
    }
  });
}
