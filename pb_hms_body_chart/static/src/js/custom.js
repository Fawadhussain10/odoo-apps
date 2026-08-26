$(document).ready(function () { 

    var pb_doc_id = $("input[name='pb_doc_id']").val();
    var pb_home_action = $("input[name='pb_home_action']").val();
    
    // Image editor
    var imageEditor = new tui.ImageEditor('#tui-image-editor-container', {
        includeUI: {
            loadImage: {
                path: '/web/content/' + pb_doc_id,
                name: 'Image',
            },
            theme: blackTheme, // or whiteTheme blackTheme
            initMenu: 'filter',
            menuBarPosition: 'bottom',
        },
        cssMaxWidth: 700,
        cssMaxHeight: 500,
        usageStatistics: false,
    });
    window.onresize = function () {
        imageEditor.ui.resizeEditor();
    };

    //replace Download image to save
    $('.tui-image-editor-header-buttons .tui-image-editor-download-btn').replaceWith('<button class="tui-image-editor-save-btn" id="PBdoSaveFile">Save</button>');
    $('.tui-image-editor-header-logo').replaceWith("<a href='" + pb_home_action + "' id='PbReturnAction' class='ml16'><img src='/pb_hms_body_chart/static/src/js/home-icon.jpeg' width='45' height='auto'><i class='fa fa-home mr-1 fa-3x'/></a>");

    // LISTEN TO THE CLICK AND SEND VIA AJAX TO THE SERVER
    $('#PBdoSaveFile').on('click', function (e) {
        //SEND TO SERVER
        var image_data = imageEditor.toDataURL();
        $.ajax({
            url: '/my/pb/image/' + pb_doc_id, // upload url
            method: "POST",
            data: imageEditor.toDataURL(),
            cache : false,
            processData: false
        }).done(function(response) {
            var link = document.getElementById('PbReturnAction');
            link.click();
        });
        return false;
    });

});