# Blender MCP Server - Extracted from addon.py for MP-03 Phase 2
# Original code by Siddharth Ahuja: www.github.com/ahujasid © 2025


import json
import socket
import threading
import time
import traceback

import bpy

from addon.utils.metrics import metrics


class BlenderMCPServer:
    """
    MCP server that listens for connections and executes commands in Blender.
    Runs in a separate thread with socket-based communication.
    """
    
    def __init__(self, host='localhost', port=9876):
        self.host = host
        self.port = port
        self.running = False
        self.socket = None
        self.server_thread = None
        # Command executor will be set by the addon
        self.command_executor = None

    def start(self):
        """Start the MCP server on configured host:port."""
        import logging
        logger = logging.getLogger("BlenderMCPServer")
        if self.running:
            logger.warning("Server is already running")
            return

        self.running = True

        try:
            # Create socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(1)

            # Start server thread
            self.server_thread = threading.Thread(target=self._server_loop)
            self.server_thread.daemon = True
            self.server_thread.start()

            logger.info(f"BlenderMCP server started on {self.host}:{self.port}")
            metrics.inc("server_start")
        except Exception as e:
            logger.error(f"Failed to start server: {str(e)}")
            metrics.inc("server_start_error")
            self.stop()

    def stop(self):
        """Stop the MCP server and cleanup resources."""
        import logging
        logger = logging.getLogger("BlenderMCPServer")
        self.running = False

        # Close socket
        if self.socket:
            try:
                self.socket.close()
            except Exception as e:
                logger.error(f"Error closing socket: {e}")
            self.socket = None

        # Wait for thread to finish
        if self.server_thread:
            try:
                if self.server_thread.is_alive():
                    self.server_thread.join(timeout=1.0)
            except Exception as e:
                logger.error(f"Error joining thread: {e}")
            self.server_thread = None

        logger.info("BlenderMCP server stopped")

    def _server_loop(self):
        """Main server loop in a separate thread."""
        import logging
        logger = logging.getLogger("BlenderMCPServer")
        logger.info("Server thread started")
        self.socket.settimeout(1.0)  # Timeout to allow for stopping

        while self.running:
            try:
                # Accept new connection
                try:
                    client, address = self.socket.accept()
                    logger.info(f"Connected to client: {address}")
                    metrics.inc("client_connected")

                    # Handle client in a separate thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client,)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                except socket.timeout:
                    # Just check running condition
                    continue
                except Exception as e:
                    logger.error(f"Error accepting connection: {str(e)}")
                    metrics.inc("accept_error")
                    time.sleep(0.5)
            except Exception as e:
                logger.error(f"Error in server loop: {str(e)}")
                metrics.inc("server_loop_error")
                if not self.running:
                    break
                time.sleep(0.5)

        logger.info("Server thread stopped")

    def _handle_client(self, client):
        """Handle connected client."""
        import logging
        logger = logging.getLogger("BlenderMCPServer")
        logger.info("Client handler started")
        client.settimeout(None)  # No timeout
        buffer = b''

        try:
            t0 = time.time()
            while self.running:
                # Receive data
                try:
                    data = client.recv(8192)
                    if not data:
                        logger.info("Client disconnected")
                        metrics.inc("client_disconnected")
                        break

                    buffer += data
                    try:
                        # Try to parse command
                        command = json.loads(buffer.decode('utf-8'))
                        buffer = b''

                        # Execute command in Blender's main thread
                        def execute_wrapper():
                            try:
                                response = self.execute_command(command)
                                response_json = json.dumps(response)
                                try:
                                    client.sendall(response_json.encode('utf-8'))
                                    metrics.inc("response_sent")
                                except Exception as e:
                                    print(f"Failed to send response - client disconnected: {e}")
                                    metrics.inc("response_send_error")
                            except Exception as e:
                                print(f"Error executing command: {str(e)}")
                                traceback.print_exc()
                                metrics.inc("command_executor_error")
                                try:
                                    error_response = {
                                        "status": "error",
                                        "message": str(e)
                                    }
                                    client.sendall(json.dumps(error_response).encode('utf-8'))
                                except Exception as e:
                                    print(f"Failed to send error response: {e}")
                                    metrics.inc("response_send_error")
                            return None

                        # Schedule execution in main thread
                        bpy.app.timers.register(execute_wrapper, first_interval=0.0)
                    except json.JSONDecodeError:
                        # Incomplete data, wait for more
                        pass
                except Exception as e:
                    print(f"Error receiving data: {str(e)}")
                    metrics.inc("client_handler_error")
                    break
        except Exception as e:
            print(f"Error in client handler: {str(e)}")
            metrics.inc("client_handler_error")
        finally:
            metrics.observe("client_handler_duration", time.time() - t0)
            try:
                client.close()
            except Exception as e:
                print(f"Error closing client connection: {e}")
            print("Client handler stopped")

    def execute_command(self, command):
        """
        Execute a command in the main Blender thread.
        Delegates to command_executor if set, otherwise returns error.
        """
        try:
            if self.command_executor:
                return self.command_executor(command)
            else:
                return {
                    "status": "error",
                    "message": "No command executor configured"
                }
        except Exception as e:
            print(f"Error executing command: {str(e)}")
            traceback.print_exc()
            return {"status": "error", "message": str(e)}
