/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class VideoCallSystrayItem extends Component {
    static template = "pb_video_call.VideoCallSystrayItem";
    static props = [];

    setup() {
        this.action = useService("action");
    }

    onClickVideoButton(event) {
        event.preventDefault();
        this.action.doAction("pb_video_call.action_pb_video_call_popup");
    }
}

registry.category("systray").add(
    "pb_video_call.VideoCallSystrayItem",
    { Component: VideoCallSystrayItem },
    { sequence: 100 }
);
