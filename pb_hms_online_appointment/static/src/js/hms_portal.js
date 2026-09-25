/** @odoo-module **/

function pbInitAppointmentPortal() {
    "use strict";

    var slot_date_input = document.querySelector("input[name='slot_date']");
    var last_date = document.querySelector("input[name='last_date']");
    var disable_dates = document.querySelector("input[name='disable_dates']");

    // yyyy-mm-dd, matching what the server sends in slot['date'] and what a
    // native <input type="date"> both stores in .value and reports to
    // 'change' handlers - no date library (moment/jquery-ui) needed or
    // available in this Odoo version.
    function toIsoDate(date) {
        var year = date.getFullYear();
        var month = String(date.getMonth() + 1).padStart(2, '0');
        var day = String(date.getDate()).padStart(2, '0');
        return year + '-' + month + '-' + day;
    }

    function isDateDisabled(isoDate) {
        return disable_dates ? disable_dates.value.indexOf(isoDate) !== -1 : false;
    }

    function selectDate(isoDate) {
        if (slot_date_input) {
            slot_date_input.value = isoDate;
        }
        var records = document.getElementsByClassName("pb_appointment_slot");
        var slot_to_show = false;
        var pb_no_slots = document.getElementsByClassName("pb_no_slots");
        for (var i = 0; i < records.length; i++) {
            var rec_date = records[i].getAttribute('data-date');
            if (isoDate === rec_date) {
                records[i].style.display = "";
                slot_to_show = true;
            } else {
                records[i].style.display = "none";
            }
        }
        if (pb_no_slots.length) {
            pb_no_slots[0].style.display = slot_to_show ? "none" : "";
        }
    }

    var datePicker = document.getElementById("PBDatePicker");
    if (datePicker) {
        var today = new Date();
        var todayIso = toIsoDate(today);
        datePicker.min = todayIso;
        if (last_date && last_date.value) {
            datePicker.max = toIsoDate(new Date(last_date.value));
        }
        datePicker.value = todayIso;

        datePicker.addEventListener('change', function () {
            if (!datePicker.value) {
                return;
            }
            if (isDateDisabled(datePicker.value)) {
                var pb_no_slots = document.getElementsByClassName("pb_no_slots");
                var records = document.getElementsByClassName("pb_appointment_slot");
                for (var i = 0; i < records.length; i++) {
                    records[i].style.display = "none";
                }
                if (pb_no_slots.length) {
                    pb_no_slots[0].style.display = "";
                }
                return;
            }
            selectDate(datePicker.value);
        });

        // Reveal whatever slots exist for today as soon as the page loads,
        // same intent as the old auto-select-today behaviour.
        selectDate(todayIso);
    }

    var isVisible = function (el) {
        return Boolean(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    };

    document.querySelectorAll('.pb_appointment_slot').forEach(function (slot) {
        slot.addEventListener('click', function () {
            var schedule_slot_input = document.querySelector("input[name='schedule_slot_id']");
            var pb_slot_selected = document.getElementsByClassName("pb_slot_selected")[0];
            var pb_slot_not_selected = document.getElementsByClassName("pb_slot_not_selected")[0];
            var wasActive = slot.classList.contains('pb_active');
            document.querySelectorAll('.pb_appointment_slot').forEach(function (el) {
                el.classList.remove('pb_active');
            });

            if (wasActive) {
                if (schedule_slot_input) {
                    schedule_slot_input.value = '';
                }
                if (typeof pb_slot_selected !== 'undefined') {
                    pb_slot_selected.style.display = "none";
                }
                if (typeof pb_slot_not_selected !== 'undefined') {
                    pb_slot_not_selected.style.display = "";
                }
            } else {
                slot.classList.add('pb_active');
                if (schedule_slot_input) {
                    schedule_slot_input.value = slot.dataset.slotlineId;
                }
                if (typeof pb_slot_selected !== 'undefined') {
                    pb_slot_selected.style.display = "";
                }
                if (typeof pb_slot_not_selected !== 'undefined') {
                    pb_slot_not_selected.style.display = "none";
                }
            }
        });
    });

    var searchInput = document.getElementById("PbRecordSearch");
    if (searchInput) {
        searchInput.addEventListener('keyup', function () {
            var filter = searchInput.value.toUpperCase();
            var records = document.getElementsByClassName("pb_physician_block");
            for (var i = 0; i < records.length; i++) {
                var rec = records[i].getElementsByClassName("pb_physician_name")[0];
                var txtValue = rec.textContent || rec.innerText;
                records[i].style.display = txtValue.toUpperCase().indexOf(filter) > -1 ? "" : "none";
                var physicians = Array.from(document.querySelectorAll('.appoint_person_panel')).filter(isVisible);
                if (physicians.length) {
                    physicians[0].click();
                }
            }
            searchInput.focus();
        });
    }

    document.querySelectorAll('.pb_appointment').forEach(function (container) {
        container.addEventListener('change', function (ev) {
            if (!ev.target.matches("input[name='appoitment_by']")) {
                return;
            }
            var physician_datas = document.getElementById('pb_physician_datas');
            var department_datas = document.getElementById('pb_department_datas');
            if (ev.target.value == 'department') {
                physician_datas && physician_datas.classList.add('pb_hide');
                department_datas && department_datas.classList.remove('pb_hide');
                var departments = document.querySelectorAll('.appoint_department_panel');
                if (departments.length) {
                    departments[0].click();
                }
            } else {
                department_datas && department_datas.classList.add('pb_hide');
                physician_datas && physician_datas.classList.remove('pb_hide');
                var physicians = document.querySelectorAll('.appoint_person_panel');
                if (physicians.length) {
                    physicians[0].click();
                }
            }
        });
    });

    var appoitment_by = document.querySelectorAll("input[name='appoitment_by']");
    appoitment_by.forEach(function (input) {
        input.dispatchEvent(new Event('change', { bubbles: true }));
    });
    appoitment_by.forEach(function (input) {
        input.checked = true;
    });
}

// Odoo's frontend module loader can finish loading/parsing this bundle after
// the document has already fired DOMContentLoaded (module scripts are
// deferred by spec) - registering a listener for an event that already
// happened means the callback silently never runs at all, with no error.
// Guard against both orderings instead of assuming one.
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', pbInitAppointmentPortal);
} else {
    pbInitAppointmentPortal();
}
