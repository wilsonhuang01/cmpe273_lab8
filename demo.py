"""Demonstrate replication, a stale read, and recovery with real client reads."""

from client import InventoryClient
from inventory import InventorySystem


def show(client):
    primary = client.read("primary")
    secondary = client.read("secondary")
    print(f"Primary: stock={primary.stock}, version={primary.version}")
    print(f"Secondary: stock={secondary.stock}, version={secondary.version}")
    return primary, secondary


def require(condition, message):
    if not condition:
        raise RuntimeError(f"FAIL: {message}")


def main():
    with InventorySystem() as inventory:
        client = InventoryClient(inventory)
        print("=== Initial inventory ===")
        show(client)

        print("\n=== 1. Normal replication: stock=12 ===")
        written = client.update(12)
        require(client.read("primary") == written, "Primary did not accept the write")
        print(f"Primary accepted: stock={written.stock}, version={written.version}")
        require(inventory.wait_for_replication(written.version), "replication timed out")
        primary, secondary = show(client)
        require(primary == secondary == written, "replicas did not converge")
        print("PASS: both replicas received the new value")

        # Establish the exact stock=10 baseline for the stale-read scenario.
        baseline = client.update(10)
        require(inventory.wait_for_replication(baseline.version), "baseline timed out")
        print("\n=== 2. Stale read: pause replication, then write stock=9 ===")
        print("Baseline: both replicas have stock=10")
        inventory.pause_replication()
        print("Replication paused")
        written = client.update(9)
        primary, secondary = show(client)
        require(primary == written and primary.stock == 9, "Primary should return 9")
        require(secondary == baseline and secondary.stock == 10, "Secondary should return 10")
        print("PASS: Secondary returns a stale read (10 while Primary returns 9)")

        print("\n=== 3. Recovery: resume replication ===")
        inventory.resume_replication()
        require(inventory.wait_for_replication(written.version), "recovery timed out")
        primary, secondary = show(client)
        require(primary == secondary == written, "recovery did not converge")
        print("PASS: both replicas converged to stock=9")


if __name__ == "__main__":
    main()
