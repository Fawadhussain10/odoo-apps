/** @odoo-module **/

function pbInitAppointmentPortal() {
    "use strict";

    var slot_date_input = $("input[name='slot_date']");
    var last_date = $("input[name='last_date']");
    var disable_dates = $("input[name='disable_dates']");

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
        return disable_dates.val().indexOf(isoDate) !== -1;
    }

    function selectDate(isoDate) {
        slot_date_input.val(isoDate);
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
        if (last_date.val()) {
            datePicker.max = toIsoDate(new Date(last_date.val()));
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

    $('.pb_appointment_slot').click(function() {
        var schedule_slot_input = $("input[name='schedule_slot_id']");
        var pb_slot_selected = document.getElementsByClassName("pb_slot_selected")[0];
        var pb_slot_not_selected = document.getElementsByClassName("pb_slot_not_selected")[0];
        var $each_appointment_slot = $(this).parents().find('.pb_appointment_slot');
        $each_appointment_slot.removeClass('pb_active')

        if ($(this).hasClass('pb_active') == true) {
            $(this).removeClass('pb_active');
            schedule_slot_input.val('');
            if (typeof pb_slot_selected !== 'undefined') {
                pb_slot_selected.style.display = "none";
            }
            if (typeof pb_slot_not_selected !== 'undefined') {
                pb_slot_not_selected.style.display = "";
            }
        } else {
            $(this).addClass('pb_active');
            var slotline_id = $(this).data('slotline-id');
            schedule_slot_input.val(slotline_id);
            if (typeof pb_slot_selected !== 'undefined') {
                pb_slot_selected.style.display = "";
            }
            if (typeof pb_slot_not_selected !== 'undefined') {
                pb_slot_not_selected.style.display = "none";
            }
        }
    });

    $("#PbRecordSearch").on('keyup', function() {
        var input, filter, records, rec, i, txtValue;
        input = document.getElementById("PbRecordSearch");
        filter = input.value.toUpperCase();
        records = document.getElementsByClassName("pb_physician_block");
        for (i = 0; i < records.length; i++) {
            rec = records[i].getElementsByClassName("pb_physician_name")[0];
            txtValue = rec.textContent || rec.innerText;
            if (txtValue.toUpperCase().indexOf(filter) > -1) {
                records[i].style.display = "";
            } else {
                records[i].style.display = "none";
            }
            var physicians = $(this).parents().find('.appoint_person_panel:visible');
            if (physicians.length) {
                physicians[0].click();
            }
        }
        var search_input = document.getElementById("PbRecordSearch");
        search_input.focus();
    });

    $('.pb_appointment').on('change', "input[name='appoitment_by']", function () {
        var appoitment_by = $(this);
        var $physician_datas = $(this).parents().find('#pb_physician_datas');
        var $department_datas = $(this).parents().find('#pb_department_datas');
        if (appoitment_by.val()=='department') {
            $physician_datas.addClass('pb_hide');
            $department_datas.removeClass('pb_hide');
            var departments = $(this).parents().find('.appoint_department_panel');
            if (departments.length) {
                departments[0].click();
            }
        } else {
            $department_datas.addClass('pb_hide');
            $physician_datas.removeClass('pb_hide');
            var physicians = $(this).parents().find('.appoint_person_panel');
            if (physicians.length) {
                physicians[0].click();
            }
        }

    });

    var appoitment_by = $("input[name='appoitment_by']");
    if (appoitment_by.length) {
        $("input[name='appoitment_by']").change();
        $("input[name='appoitment_by']").attr('checked', true);
    }
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
