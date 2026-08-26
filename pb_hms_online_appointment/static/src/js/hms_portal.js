/** @odoo-module **/

document.addEventListener('DOMContentLoaded', function () {
    "use strict";

    var slot_date_input = $("input[name='slot_date']");
    var last_date = $("input[name='last_date']");
    
    var disable_dates = $("input[name='disable_dates']");

    function DisableDates(date) {
        var string = jQuery.datepicker.formatDate('yy-mm-dd', date);
        return [disable_dates.val().indexOf(string) == -1];
    }

    var languages = document.getElementsByClassName("js_change_lang active");
    if (languages.length > 0) { 
        var lang = languages[0].getAttribute('data-url_code', '');
        if (lang.startsWith('es')) {        
            $.datepicker.regional['es'] = {
                closeText: 'Cerrar',
                prevText: '< Ant',
                nextText: 'Sig >',
                currentText: 'Hoy',
                monthNames: ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'],
                monthNamesShort: ['Ene','Feb','Mar','Abr', 'May','Jun','Jul','Ago','Sep', 'Oct','Nov','Dic'],
                dayNames: ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'],
                dayNamesShort: ['Dom','Lun','Mar','Mié','Juv','Vie','Sáb'],
                dayNamesMin: ['Do','Lu','Ma','Mi','Ju','Vi','Sá'],
                weekHeader: 'Sm',
                dateFormat: 'yy-mm-dd',
                firstDay: 1,
                isRTL: false,
                showMonthAfterYear: false,
                yearSuffix: ''
            };
            $.datepicker.setDefaults($.datepicker.regional['es']);
        }
    }

    $("#PBDatePicker").datepicker({
        numberOfMonths: 1,
        format: 'yyyy-mm-dd',
        beforeShowDay: DisableDates,
        onSelect: function(date) {
            slot_date_input.val(date);
            var selected_date = moment(date).format('YYYY-MM-DD');
            var records = document.getElementsByClassName("pb_appointment_slot");
            var i;
            var slot_to_show = false;
            var pb_no_slots = document.getElementsByClassName("pb_no_slots");
            for (i = 0; i < records.length; i++) {
                var rec_date = records[i].getAttribute('data-date');
                if (selected_date==rec_date) {
                    records[i].style.display = "";
                    slot_to_show = true;
                } else {
                    records[i].style.display = "none";
                }
            }
            if (slot_to_show==true) {
                pb_no_slots[0].style.display = "none";
            } else {
                pb_no_slots[0].style.display = "";
            }
        },
        minDate: new Date(),
        maxDate: new Date(last_date.val()),
        selectWeek: true,
        inline: true,
    });

    $('.ui-datepicker-current-day').click();
    slot_date_input.val(new Date());

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


});