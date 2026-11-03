import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import CustomerModal from "../CustomerModal";

describe("CustomerModal telephone identity", () => {
  it("creates a telephone-only customer without truncating international numbers", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<CustomerModal onSave={onSave} onClose={vi.fn()} />);

    await user.type(screen.getByLabelText("Telephone *"), "+94 77 123 4567");
    await user.click(screen.getByRole("button", { name: "Create Customer" }));

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      phone: "+94 77 123 4567",
      email: null,
    }));
  });

  it("requires a telephone before creating a customer", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<CustomerModal onSave={onSave} onClose={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Email (optional)"), {
      target: { value: "customer@example.com" },
    });
    await user.click(screen.getByRole("button", { name: "Create Customer" }));

    expect(screen.getByLabelText("Telephone *")).toBeInvalid();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("sends null when an existing customer's optional email is cleared", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<CustomerModal
      customer={{ phone: "0771234567", email: "customer@example.com" }}
      onSave={onSave}
      onClose={vi.fn()}
    />);

    await user.clear(screen.getByLabelText("Email (optional)"));
    await user.click(screen.getByRole("button", { name: "Save Changes" }));

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      phone: "0771234567",
      email: null,
    }));
  });

  it("lets an email-only legacy customer update unrelated fields without supplying a phone", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<CustomerModal
      customer={{ phone: null, email: "customer@example.com", company_name: "Old Company" }}
      onSave={onSave}
      onClose={vi.fn()}
    />);

    fireEvent.change(screen.getByDisplayValue("Old Company"), {
      target: { value: "New Company" },
    });
    await user.click(screen.getByRole("button", { name: "Save Changes" }));

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ company_name: "New Company" }));
    expect(onSave.mock.calls[0][0]).not.toHaveProperty("phone");
  });

  it("does not allow an existing customer's telephone to be cleared", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<CustomerModal
      customer={{ phone: "0771234567", email: null }}
      onSave={onSave}
      onClose={vi.fn()}
    />);

    await user.clear(screen.getByLabelText("Telephone *"));
    await user.click(screen.getByRole("button", { name: "Save Changes" }));

    expect(screen.getByLabelText("Telephone *")).toBeInvalid();
    expect(onSave).not.toHaveBeenCalled();
  });
});
