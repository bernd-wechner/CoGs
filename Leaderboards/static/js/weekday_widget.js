// Taken from: https://jsfiddle.net/schinckel/gge7v234/
// And modernised and simplified a little
//
// Some nomenclature:
// 	Days are Sunday,Monday,Tuesday,Wednesday,Thursday,Friday,Saturday
// 	Parts are Any Day, Weekends, Weekdays

class WeekdayWidget {
    constructor(element) {
        this.element = element;
        this.parts = Array.from(element.querySelectorAll('.week-parts [type=checkbox]'));
        this.days = Array.from(element.querySelectorAll('.days [type=checkbox]'));

        element.addEventListener('change', this.click_event_handler.bind(this));
    }

    click_event_handler(event) {
        if (event.target.tagName === 'INPUT') {
            if (event.target.name === this.element.dataset.name) {
                this.updateParts();
            } else {
                this.updateDays(event.target.dataset.values.split(','), event.target.checked);
                this.updateParts();
            }
        }
    }

    updateParts() {
        const selected = this.days.filter(e => e.checked).map(e => e.value);

        this.parts.forEach(function(part) {
            const partDays = part.dataset.values.split(',');
            const notSelectedParts = partDays.filter(d => selected.indexOf(d) === -1);
            if (notSelectedParts.length === 0) {
                part.checked = true;
                part.indeterminate = false;
            } else if (notSelectedParts.length === partDays.length) {
                part.checked = false;
                part.indeterminate = false;
            } else {
                part.indeterminate = true;
            }
        });
    }

    updateDays(values, checked) {
        this.days.forEach(function(e) {
            if (values.indexOf(e.value) > -1) {
                e.checked = checked;
            }
        });
    }
}