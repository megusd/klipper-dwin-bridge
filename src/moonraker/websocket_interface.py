 # 
 # This file is part of python-dgus (https://github.com/seho85/python-dgus).
 # Copyright (c) 2022 Sebastian Holzgreve
 # 
 # This program is free software: you can redistribute it and/or modify  
 # it under the terms of the GNU General Public License as published by  
 # the Free Software Foundation, version 3.
 #
 # This program is distributed in the hope that it will be useful, but 
 # WITHOUT ANY WARRANTY; without even the implied warranty of 
 # MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU 
 # General Public License for more details.
 #
 # You should have received a copy of the GNU General Public License 
 # along with this program. If not, see <http://www.gnu.org/licenses/>.
 #
 
from distutils.log import error
        response = json.loads(msg)
        # Use defensive gets to tolerate varying Moonraker responses
        resp_id = response.get("id")

        if resp_id is not None:
            # Response to our query data request
            if resp_id == WebsocktRequestId.QUERY_PRINTER_OBJECTS:
                status = response.get("result", {}).get("status")
                if status is not None:
                    with self.json_resouce_lock:
                        json_merged = merge(self.json_data_modell, status)
                        self.json_data_modell = json_merged
                    self.add_subscription(ws_app)
                else:
                    self._logger.warning("Missing key: response.result.status")

            if resp_id == WebsocktRequestId.QUERY_SERVER_INFO:
                result = response.get("result", {})
                if result:
                    with self.json_resouce_lock:
                        existing = self.json_data_modell.get("server_info", {}) if isinstance(self.json_data_modell, dict) else {}
                        try:
                            json_merged = merge(existing, result)
                            self.json_data_modell["server_info"] = json_merged
                        except Exception:
                            self._logger.exception("Failed to merge server_info response")
                            self.json_data_modell["server_info"] = result
                else:
                    self._logger.warning("Missing key: response.result for server_info query")

            if resp_id == WebsocktRequestId.QUERY_PRINTER_INFO:
                result = response.get("result", {})
                state_string = result.get("state")
                state_message = result.get("state_message")
                if state_string is None:
                    self._logger.warning("Missing key: response.result.state")
                else:
                    klippy_state = KlippyState.get_state_for_string(state_string)
                    if klippy_state != self._klippy_state or state_message != self._klippy_state_text:
                        self._set_klippy_state(klippy_state, state_message)

            if self._current_request is not None:
                current_req_id = None
                try:
                    current_req_id = self._current_request.request.get("id") if isinstance(self._current_request.request, dict) else None
                except Exception:
                    current_req_id = None

                if current_req_id is not None and resp_id == current_req_id:
                    try:
                        self._current_request.response_received_callback(response)
                    except Exception:
                        self._logger.exception("Error in current request response callback")
                    self._current_request = None

        method = response.get("method")
        if method is not None:
            if method == "notify_status_update":
                params = response.get("params", [])
                if not params:
                    self._logger.warning("Missing key: response.params for notify_status_update")
                else:
                    json_pub_data = params[0]
                    try:
                        json_merged = merge(self.json_data_modell, json_pub_data)
                        with self.json_resouce_lock:
                            printer_state_string = str(json_merged.get("print_stats", {}).get("state"))
                            read_printer_state = PrinterState.get_state_for_string(printer_state_string)
                            if self._printer_state != read_printer_state:
                                self._set_printer_state(read_printer_state)
                            self.json_data_modell = json_merged
                    except Exception:
                        self._logger.exception("Failed to process notify_status_update payload")

            if method == "notify_klippy_ready":
                self.add_subscription(ws_app)
                self._logger.info("Received: notifiy_klippy_ready")
                self._set_klippy_state(KlippyState.READY)

            if method == "notify_klippy_shutdown":
                self._logger.info("Received: notifiy_klippy_shutdown")
                self._set_klippy_state(KlippyState.SHUTDOWN)

            if method == "notify_klippy_disconnected":
                self._logger.info("Received: notifiy_klippy_disconnected")
                self._set_klippy_state(KlippyState.DISCONNECTED)

        def on_message(ws_app, msg):
            self.ws_on_message(ws_app,msg)

        def on_open(ws_app):
            self.ws_on_open(ws_app)

        self.ws_app = WebSocketApp(
            url=ws_url,
            on_close=on_close,
            on_error=on_error,
            on_message=on_message,
            on_open=on_open
        )


    def start(self):
        self.thread = Thread(target=self.ws_app.run_forever)
        self.thread.start()
        self.cyclic_query_thread_running = True
        self.cyclic_query_thread = Thread(target=self.cyclic_query_thread_function)
        self.cyclic_query_thread.start()
        

    def cyclic_query_thread_function(self):
        while self.cyclic_query_thread_running:
            
            if self.open:
            
                query_server_info_json = {
                    "jsonrpc": "2.0",
                    "method": "server.info",
                    "id": WebsocktRequestId.QUERY_SERVER_INFO
                }

                #print("send cyclic query...")

            
                self.ws_app.send(json.dumps(query_server_info_json))


                query_server_info_json = {
                    "jsonrpc": "2.0",
                    "method": "printer.info",
                    "id": WebsocktRequestId.QUERY_PRINTER_INFO
                }

                self.ws_app.send(json.dumps(query_server_info_json))

                if not self._requests.empty():
                    if self._current_request is None:
                        self._current_request = self._requests.get()
                        self.ws_app.send(json.dumps(self._current_request.request))
                        self._current_request.request_was_send_callback()

            
            

            sleep(1)

    
    def stop(self):
        self.cyclic_query_thread_running = False
        self.cyclic_query_thread.join()
        self._logger.info("Stopped cyclic query thread...")
        
        self.ws_app.close()
        self.thread.join()
        self._logger.info("Stopped Websocket Communication....")
        

    def ws_on_open(self, ws_app):
        self.open = True
        self._logger.info("Connection to Moonraker websocket established...")
        self.send_query(ws_app)

    def ws_on_close(self,ws_app, close_status, close_msg):
        self.open = False

        self._logger.error("Websocket onClose %s, %s", close_status, close_msg)

        self.cyclic_query_thread_running = False
        self.cyclic_query_thread.join()

        self.start()

    def ws_on_error(self, ws_app, error):
        self._logger.critical("Websockt Error %s: %s", ws_app, error)

    def ws_on_message(self, ws_app, msg):
        response = json.loads(msg)
        # Defensive access to response keys to avoid KeyErrors
        resp_id = response.get("id", None)

        if resp_id is not None:
            # Handle QUERY_PRINTER_OBJECTS
            if resp_id == WebsocktRequestId.QUERY_PRINTER_OBJECTS:
                status = None
                result = response.get("result")
                if result is None:
                    self._logger.debug("Missing key: response.result for QUERY_PRINTER_OBJECTS; using default None")
                else:
                    status = result.get("status")
                    if status is None:
                        self._logger.debug("Missing key: response.result.status for QUERY_PRINTER_OBJECTS; using default None")

                if status is not None:
                    with self.json_resouce_lock:
                        try:
                            json_merged = merge(self.json_data_modell, status)
                            self.json_data_modell = json_merged
                        except Exception:
                            self._logger.exception("Failed to merge printer objects status")
                    self.add_subscription(ws_app)

            # Handle QUERY_SERVER_INFO
            if resp_id == WebsocktRequestId.QUERY_SERVER_INFO:
                result = response.get("result", {})
                if not result:
                    self._logger.debug("Missing key: response.result for QUERY_SERVER_INFO; storing empty result")
                with self.json_resouce_lock:
                    existing = self.json_data_modell.get("server_info", {}) if isinstance(self.json_data_modell, dict) else {}
                    try:
                        json_merged = merge(existing, result)
                        self.json_data_modell["server_info"] = json_merged
                    except Exception:
                        self._logger.exception("Failed to merge server_info response")
                        self.json_data_modell["server_info"] = result

            # Handle QUERY_PRINTER_INFO
            if resp_id == WebsocktRequestId.QUERY_PRINTER_INFO:
                result = response.get("result", {})
                if not result:
                    self._logger.debug("Missing key: response.result for QUERY_PRINTER_INFO; using default empty dict")
                state_string = result.get("state") if isinstance(result, dict) else None
                state_message = result.get("state_message") if isinstance(result, dict) else ""
                if state_string is None:
                    self._logger.debug("Missing key: response.result.state for QUERY_PRINTER_INFO; skipping state update")
                else:
                    klippy_state = KlippyState.get_state_for_string(state_string)
                    if klippy_state != self._klippy_state or state_message != self._klippy_state_text:
                        self._set_klippy_state(klippy_state, state_message)

            # Handle current request responses
            if self._current_request is not None:
                try:
                    current_req_id = self._current_request.request.get("id") if isinstance(self._current_request.request, dict) else None
                except Exception:
                    current_req_id = None

                if current_req_id is not None and resp_id == current_req_id:
                    try:
                        self._current_request.response_received_callback(response)
                    except Exception:
                        self._logger.exception("Error in current request response callback")
                    self._current_request = None

        method = response.get("method")
        if method is not None:
            if method == "notify_status_update":
                params = response.get("params", [])
                if not params:
                    self._logger.debug("Missing key: response.params for notify_status_update; skipping")
                else:
                    json_pub_data = params[0]
                    try:
                        json_merged = merge(self.json_data_modell, json_pub_data)
                        with self.json_resouce_lock:
                            printer_state_string = str(json_merged.get("print_stats", {}).get("state"))
                            read_printer_state = PrinterState.get_state_for_string(printer_state_string)
                            if self._printer_state != read_printer_state:
                                self._set_printer_state(read_printer_state)
                            self.json_data_modell = json_merged
                    except Exception:
                        self._logger.exception("Failed to process notify_status_update payload")

            if method == "notify_klippy_ready":
                self.add_subscription(ws_app)
                self._logger.info("Received: notifiy_klippy_ready")
                self._set_klippy_state(KlippyState.READY)

            if method == "notify_klippy_shutdown":
                self._logger.info("Received: notifiy_klippy_shutdown")
                self._set_klippy_state(KlippyState.SHUTDOWN)

            if method == "notify_klippy_disconnected":
                self._logger.info("Received: notifiy_klippy_disconnected")
                self._set_klippy_state(KlippyState.DISCONNECTED)



    def send_query(self, ws):
       
        self.ws_app.send(json.dumps(self.query_req))

    def unsubscribe_all(self, ws):
        data = {
            "jsonrpc": "2.0",
            "method": "printer.objects.subscribe",
            "params": {
                "objects": { },
            },
            "id": WebsocktRequestId.UNSUBSCRIBE_PRINTER_OBJECTS
        }

        self.ws_app.send(json.dumps(data))


    def add_subscription(self, ws):
        self.ws_app.send(json.dumps(self.subscription_request))

    def write_json_config(self, websocket_json_config):

        with open(websocket_json_config, "w") as json_file:
            json_file.write(json.dumps(self.to_json(), indent=3))

    def read_json_config(self, websocket_json_config):

        try:
            with open(websocket_json_config) as json_file:
                json_data = json.load(json_file)
                return self.from_json(json_data)

        except FileNotFoundError:
            self._logger.critical("Unable to read configuration from %s", websocket_json_config)
            return False
            


    def get_klipper_data(self, klipper_data : list, array_index : int = -1):
        with self.json_resouce_lock:
            json_obj = self.json_data_modell
            for dp in klipper_data:
                if not isinstance(json_obj, dict):
                    self._logger.debug("Expected dict while traversing klipper data path, got %s", type(json_obj))
                    return None
                json_obj = json_obj.get(dp)
                if json_obj is None:
                    self._logger.warning("Missing key in klipper data path: %s", dp)
                    return None

            if array_index >= 0:
                json_obj = json_obj[array_index]
            return json_obj


    def queue_request(self, request : MoonrakerRequest):
        self._requests.put(request)
    #JsonSerializable implementation

    def from_json(self, json_data : dict):
        websocket_object = json_data.get("websocket")
        if websocket_object is None:
            print("Malformed Websocket.json: 'websocket' entry is missing!")
            return False
        
        ip_object = websocket_object.get("ip")
        if ip_object is None:
            print("Malformed Websocket.json: Missing 'ip' entry!")
            return False

        port_object = websocket_object.get("port")
        if port_object is None:
            print("Malformed JSON: Missing 'port' entry!")
            return False


        printer_objects_object = websocket_object.get("printer_objects")
        if printer_objects_object is None:
            print("Malformed JSON: Missing 'printer_objects' entry!")
            return False

        data_modell_object = websocket_object.get("data_model")
        if data_modell_object is None:
            print("Malformed JSON: Missing 'data_model' entry!")
            return False

        self.query_req["params"]["objects"] = printer_objects_object
        self.subscription_request["params"]["objects"] = printer_objects_object
        self.json_data_modell = data_modell_object

        self.printer_ip = ip_object
        self.port = port_object

        self.create_websocket()

        return True

    def to_json(self):
        websocket_json = {
            "websocket" : {
                "ip" : self.printer_ip,
                "port" : self.port,
                "printer_objects" : self.query_req["params"]["objects"],
                "data_model" : self.json_data_modell
            }
        }

        return websocket_json

    def _set_klippy_state(self, state : KlippyState, state_message = ""):
        self._klippy_state = state
        self._klippy_state_text = state_message
        self._logger.info("KlippyState Changed: %s", self._klippy_state)
        self._logger.info("State Message: %s", state_message.replace("\n", " "))

        for cb in self._klippy_event_changed_callbacks:
            cb(state, state_message)
      


    def register_klippy_state_event_receiver(self, callback : Callable[[KlippyState, str], Any]):
        self._klippy_event_changed_callbacks.append(callback)



    def _set_printer_state(self, state : PrinterState, error_msg = ""):
        
        self._printer_state = state
        self._printer_error_text = error_msg

        self._logger.info("PrinterState Changed: %s", self._printer_state)
        if self._printer_state == PrinterState.ERROR:
            self._logger.info("Error Message: %s", error_msg.replace("\n", " "))

        for callback in self._printer_state_event_changed_callbacks:
            callback(state, error_msg)


    def register_printer_state_event_receiver(self, callback : Callable[[PrinterState, str], Any]):
        self._printer_state_event_changed_callbacks.append(callback)