import socket
import threading


def handle_client(client_socket):
    ollama_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        ollama_socket.connect(("127.0.0.1", 11434))
    except Exception as e:
        print(f"Failed to connect to local Ollama: {e}")
        client_socket.close()
        return

    def forward(src, dest):
        try:
            while True:
                data = src.recv(4096)
                if not data:
                    break
                dest.sendall(data)
        except Exception:
            pass
        finally:
            try:
                src.close()
            except:
                pass
            try:
                dest.close()
            except:
                pass

    t1 = threading.Thread(target=forward, args=(client_socket, ollama_socket))
    t2 = threading.Thread(target=forward, args=(ollama_socket, client_socket))
    t1.daemon = True
    t2.daemon = True
    t1.start()
    t2.start()


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("192.168.15.20", 11434))
    server.listen(10)
    print("Port forwarder listening on 192.168.15.20:11434 -> 127.0.0.1:11434")
    try:
        while True:
            client, addr = server.accept()
            handle_client(client)
    except KeyboardInterrupt:
        pass
    finally:
        server.close()


if __name__ == "__main__":
    main()
