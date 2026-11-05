from locust import HttpUser, task, between

class MARGUser(HttpUser):
    wait_time = between(1, 3)

    @task(5)
    def home(self):
        self.client.get("/")

    @task(3)
    def login(self):
        self.client.post(
            "/login",
            json={"email": "loadtester@example.com", "password": "LoadPass123"},
            name="/login (POST)"
        )

    @task(2)
    def signup(self):
        self.client.post(
            "/signup",
            json={
                "name": "Load User",
                "email": "newloaduser@example.com",
                "phone": "1234567890",
                "password": "LoadPass123"
            },
            name="/signup (POST)"
        )

    @task(1)
    def profile(self):
        self.client.get("/profile", headers={"Authorization": "Bearer <token>"})
