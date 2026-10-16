import Base

# Upstream Bend 2 parallelism example, used only as a GPU toolchain smoke test.
# NOT an Airtable graph kernel or a benchmark of VC workflow throughput.
def pow2(+n: Nat) -> U32:
  match n:
    case 0 n:
      1
    case 1 n+p:
      a b = pow2(p) pow2(p)
      (a + b : U32)

def main() -> IO(Unit):
  IO.print(U32.show(pow2!(20 n)))
