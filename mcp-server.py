from fastmcp import FastMCP

mcp = FastMCP(name="calculator")

@mcp.tool
def multiply(a: float, b: float) -> float:
    """
        Multiplies two numbers together.
        Args:
            a (float): The first number.
            b (float): The second number.
        Returns:
            float: The product of the two numbers.
    """
    return a * b

if __name__ == "__main__":
    mcp.run(transport="stdio")