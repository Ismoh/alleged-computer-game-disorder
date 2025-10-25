import datetime
import dearpygui.dearpygui as dpg
import json
import logging
import os
import psutil
import schedule
import threading
import time

from tzlocal import get_localzone

conf = {}
conf["exclusions"] = {}
conf["time_to_sleep"] = None
conf["snooze"] = None
time_left_text_tag = -1
time_left = "00:00"

logger = logging.getLogger(__name__)
logging.basicConfig(filename="acgd.log", encoding="utf-8", level=logging.DEBUG)
logger.info("Init...")


def save_config():
    with open("acgd.conf", "w") as fp:
        json.dump(conf, fp)
        logger.info("config saved")


def load_config():
    global conf
    try:
        with open("acgd.conf", "r") as fp:
            conf = json.load(fp)
            logger.info("config loaded")
    except Exception as e:
        with open("acgd.conf", "w") as fp:
            fp.write("")
            logger.info("config created")


def sort_callback(sender, sort_specs):
    print("Sender: ", sender)
    print("App Data: ", sort_specs)

    # sort_specs scenarios:
    #   1. no sorting -> sort_specs == None
    #   2. single sorting -> sort_specs == [[column_id, direction]]
    #   3. multi sorting -> sort_specs == [[column_id, direction], [column_id, direction], ...]
    #
    # notes:
    #   1. direction is ascending if == 1
    #   2. direction is ascending if == -1

    # no sorting case
    if sort_specs is None:
        return

    rows = dpg.get_item_children(sender, 1)

    # create a list that can be sorted based on first cell
    # value, keeping track of row and value used to sort
    sortable_list = []
    for row in rows:
        first_cell = dpg.get_item_children(row, 1)[0]
        sortable_list.append([row, dpg.get_value(first_cell)])

    def _sorter(e):
        return e[1]

    sortable_list.sort(key=_sorter, reverse=sort_specs[0][1] < 0)

    # create list of just sorted row ids
    new_order = []
    for pair in sortable_list:
        new_order.append(pair[0])

    dpg.reorder_items(sender, 1, new_order)
    logger.info("table sorted")


def file_dialog_callback(sender, app_data):
    global conf

    if "" == app_data["file_name"].split(".")[0]:
        # user selected nothing and clicked OK
        return

    conf["exclusions"][app_data["file_name"]] = app_data["file_path_name"]
    set_table_data("ExclusionTable", conf["exclusions"])
    logger.info("table data set")
    save_config()


def input_text_time_to_sleep_callback(input_text_tag):
    global conf
    conf["time_to_sleep"] = dpg.get_value(input_text_tag)
    logger.info("time to sleep set")
    save_config()


def input_text_snooze_callback(input_text_tag):
    global conf
    conf["snooze"] = dpg.get_value(input_text_tag)
    logger.info("snooze set")
    save_config()


def lets_go_callback():
    save_config()
    current_timezone = get_localzone()
    zone = current_timezone.key
    out = schedule.every().day.at(str(conf["time_to_sleep"]), zone).do(shutdown)
    logger.info("timer started")
    t1 = threading.Thread(name="schedule", target=schedule_run)
    t1.start()


def delete_row(tag, k):
    parent_tag = dpg.get_item_parent(tag)
    dpg.delete_item(parent_tag)
    logger.info("table entry removed")
    save_config()


def clear_table(table_tag):
    for tag in dpg.get_item_children(table_tag)[1]:
        dpg.delete_item(tag)
    logger.info("table cleared")


def set_table_data(tag, data):
    clear_table(tag)
    for i, k in enumerate(data):
        row_tag = f"row_{i}"
        with dpg.table_row(parent=tag, tag=row_tag):
            dpg.add_text(k)
            dpg.add_text(data[k])
            tag_id = dpg.add_button(label="-", callback=delete_row)
    logger.info("table new data set")


def process_exists(process_name):
    processes = list(p.name() for p in psutil.process_iter())
    if process_name in processes:
        logger.info(f"{process_name} is running")
        return True
    return False


def schedule_run():
    global conf
    global time_left_text_tag
    global time_left

    while True:
        schedule.run_pending()
        now = datetime.datetime.now()
        now_datetime_str = datetime.datetime.strptime(
            f"{now.year}.{now.month}.{now.day}-{now.hour}:{now.minute}:{now.second}",
            "%Y.%m.%d-%H:%M:%S",
        )

        sleep_hour = conf["time_to_sleep"].split(":")[0]
        sleep_minute = conf["time_to_sleep"].split(":")[1]
        sleep_datetime_str = datetime.datetime.strptime(
            f"{now.year}.{now.month}.{now.day}-{sleep_hour}:{sleep_minute}:{now.second}",
            "%Y.%m.%d-%H:%M:%S",
        )

        diff = (sleep_datetime_str - now_datetime_str).total_seconds()
        if diff < 0:
            now_datetime_str = datetime.datetime.strptime(
                f"{now.year}.{now.month}.{now.day}-{now.hour}:{now.minute}:{now.second}",
                "%Y.%m.%d-%H:%M:%S",
            )

            sleep_hour = conf["time_to_sleep"].split(":")[0]
            sleep_minute = conf["time_to_sleep"].split(":")[1]
            sleep_datetime_str = datetime.datetime.strptime(
                f"{now.year}.{now.month}.{now.day+1}-{sleep_hour}:{sleep_minute}:{now.second}",
                "%Y.%m.%d-%H:%M:%S",
            )
            diff = (sleep_datetime_str - now_datetime_str).total_seconds()

        diff_time = time.gmtime(diff)
        time_left = time.strftime("%Hh:%Mm left..", diff_time)
        logger.info(f"timer = {time_left}")
        dpg.set_value(time_left_text_tag, time_left)
        time.sleep(1)


def shutdown():
    snooze = 900
    for k in conf["exclusions"]:
        p = k
        if process_exists(p):
            snooze = conf["snooze"] * 60
    os.system(f"shutdown /s /t {snooze}")
    logger.info("shuting down")


def main():
    global conf
    global time_left_text_tag

    load_config()

    dpg.create_context()

    with dpg.window(tag="Primary Window"):
        dpg.add_text("Time to sleep:")
        time_to_sleep_input = dpg.add_input_text(
            label="HH:MM", default_value=conf["time_to_sleep"]
        )
        dpg.add_button(
            label="Save..",
            callback=lambda: input_text_time_to_sleep_callback(time_to_sleep_input),
        )

        dpg.add_text("Set warning snooze (in Minutes):")
        snooze_input = dpg.add_input_text(label="MM", default_value=conf["snooze"])
        dpg.add_button(
            label="Save..", callback=lambda: input_text_snooze_callback(snooze_input)
        )

        dpg.add_button(
            label="Add exclusion", callback=lambda: dpg.show_item("file_dialog_tag")
        )
        dpg.add_text(
            "An exclusion will interrupt the shutdown, as long as the app is running."
        )
        table_tag = "ExclusionTable"
        with dpg.table(
            tag=table_tag,
            header_row=True,
            resizable=True,
            policy=dpg.mvTable_SizingStretchProp,
            borders_outerH=True,
            borders_innerV=True,
            borders_innerH=True,
            borders_outerV=True,
            sortable=True,
            callback=sort_callback,
        ):
            dpg.add_table_column(label="Name")
            dpg.add_table_column(label="Path")
            dpg.add_table_column(label="Actions", no_sort=True)
            # once it reaches the end of the columns
            for i, k in enumerate(conf["exclusions"]):
                row_tag = f"row_{i}"
                with dpg.table_row(parent=table_tag, tag=row_tag):
                    dpg.add_text(k)
                    dpg.add_text(conf["exclusions"][k])
                    tag_id = dpg.add_button(label="-", callback=delete_row)

        dpg.add_button(label="Lets go!", callback=lets_go_callback)
        time_left_text_tag = dpg.add_text(label="Time left")

    with dpg.file_dialog(
        directory_selector=False,
        show=False,
        callback=file_dialog_callback,
        file_count=3,
        tag="file_dialog_tag",
        width=700,
        height=400,
    ):
        dpg.add_file_extension(".exe", color=(0, 255, 0, 255))

    dpg.create_viewport(title="alleged computer game disorder", width=1024, height=768)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("Primary Window", True)
    dpg.start_dearpygui()
    dpg.destroy_context()


if __name__ == "__main__":
    main()
