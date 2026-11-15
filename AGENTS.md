
# Environment
Managed by direnv. Use the following to run commands properly:
```
% direnv exec . <command>
```

# Relationship to Zuspec
- fw-hdl is just a front-end
- Prefer representing something in Zuspec to directly in fw-hdl
- Prefer performing a manipulation on Zuspec IR to writing bespoke code in fw-hdl
